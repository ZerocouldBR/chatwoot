require 'rails_helper'

# ServiceDesk M5: a macro preenche o editor (macro_fill_editor) e as ações novas.
RSpec.describe Macros::ExecutionService do
  let(:account) { create(:account) }
  let(:conversation) { create(:conversation, account: account, status: :open) }
  let(:user) { create(:user, account: account, role: :administrator) }
  let(:team) { create(:team, account: account) }

  def run(actions)
    macro = create(:macro, account: account, actions: actions)
    described_class.new(macro, conversation, user).perform
    conversation.reload
  end

  before do
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_tabulacao', attribute_display_type: 'list',
                                         attribute_values: %w[Chargeback Estorno])
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_status', attribute_display_type: 'list',
                                         attribute_values: %w[Aberto Pendente Desenvolvimento Resolvido Concluído])
  end

  describe 'macro_fill_editor' do
    let(:reply_and_actions) do
      [
        { 'action_name' => 'send_message', 'action_params' => ['Olá {{contact.name}}'] },
        { 'action_name' => 'add_private_note', 'action_params' => ['Nota interna'] },
        { 'action_name' => 'assign_team', 'action_params' => [team.id] },
        { 'action_name' => 'set_custom_attribute', 'action_params' => %w[zd_tabulacao Chargeback] },
        { 'action_name' => 'set_ticket_status', 'action_params' => ['Desenvolvimento'] }
      ]
    end

    context 'when enabled (installation default)' do
      it 'does not send the reply but applies the other actions' do
        expect { run(reply_and_actions) }.not_to(change { conversation.messages.outgoing.where(private: false).count })

        expect(conversation.team).to eq(team)
        expect(conversation.custom_attributes).to include('zd_tabulacao' => 'Chargeback', 'zd_status' => 'Desenvolvimento')
        expect(conversation.status).to eq('on_hold')
      end

      it 'keeps posting the private note when the macro also has a public reply' do
        run(reply_and_actions)

        expect(conversation.messages.outgoing.where(private: true).pluck(:content)).to eq(['Nota interna'])
      end

      it 'leaves the private note for the editor when it is the only text of the macro' do
        expect do
          run([{ 'action_name' => 'add_private_note', 'action_params' => ['Só nota'] },
               { 'action_name' => 'resolve_conversation', 'action_params' => [] }])
        end.not_to(change { Message.outgoing.count })

        expect(conversation.status).to eq('resolved')
      end

      it 'never sends the attachments of the macro' do
        macro = create(:macro, account: account, actions: [])
        macro.files.attach(io: Rails.root.join('spec/assets/avatar.png').open, filename: 'avatar.png', content_type: 'image/png')
        macro.update!(actions: [{ 'action_name' => 'send_attachment', 'action_params' => [macro.files.first.blob_id] }])

        expect { described_class.new(macro, conversation, user).perform }.not_to(change { Message.outgoing.count })
      end
    end

    context 'when disabled in the account settings' do
      before { account.update!(macro_fill_editor: false) }

      it 'keeps the upstream behaviour and sends the reply right away' do
        run(reply_and_actions)

        expect(conversation.messages.outgoing.where(private: false).last.content).to start_with('Olá')
      end
    end

    context 'when disabled for the installation' do
      it 'follows SD_MACRO_FILL_EDITOR when the account has no value' do
        with_modified_env(SD_MACRO_FILL_EDITOR: 'false') do
          run(reply_and_actions)
        end

        expect(conversation.messages.outgoing.where(private: false).count).to eq(1)
      end
    end
  end

  describe '#set_custom_attribute' do
    it 'merges the value into the custom attributes' do
      conversation.update!(custom_attributes: { 'outro' => 'x' })

      run([{ 'action_name' => 'set_custom_attribute', 'action_params' => %w[zd_tabulacao Estorno] }])

      expect(conversation.custom_attributes).to eq('outro' => 'x', 'zd_tabulacao' => 'Estorno')
    end

    it 'clears the attribute with a blank value' do
      conversation.update!(custom_attributes: { 'zd_tabulacao' => 'Estorno' })

      run([{ 'action_name' => 'set_custom_attribute', 'action_params' => ['zd_tabulacao', ''] }])

      expect(conversation.custom_attributes).not_to have_key('zd_tabulacao')
    end

    it 'ignores a value that is no longer in the list' do
      macro = create(:macro, account: account, actions: [])
      macro.actions = [{ 'action_name' => 'set_custom_attribute', 'action_params' => %w[zd_tabulacao Removida] }]
      macro.save!(validate: false)

      described_class.new(macro, conversation, user).perform

      expect(conversation.reload.custom_attributes).not_to have_key('zd_tabulacao')
    end
  end

  describe '#set_ticket_status' do
    it 'writes the label and the canonical native status' do
      run([{ 'action_name' => 'set_ticket_status', 'action_params' => ['Concluído'] }])

      expect(conversation.custom_attributes['zd_status']).to eq('Concluído')
      expect(conversation.status).to eq('resolved')
    end

    it 'reopens with an open category label' do
      conversation.update!(status: :resolved, custom_attributes: { 'zd_status' => 'Resolvido' })

      run([{ 'action_name' => 'set_ticket_status', 'action_params' => ['Aberto'] }])

      expect(conversation.status).to eq('open')
      expect(conversation.custom_attributes['zd_status']).to eq('Aberto')
    end
  end

  describe '#change_subject' do
    it 'stores the subject in mail_subject' do
      conversation.update!(additional_attributes: { 'mail_subject' => 'Antigo', 'source' => 'email' })

      run([{ 'action_name' => 'change_subject', 'action_params' => ['Reserva 123 - cancelamento'] }])

      expect(conversation.additional_attributes).to eq('mail_subject' => 'Reserva 123 - cancelamento', 'source' => 'email')
    end
  end
end
