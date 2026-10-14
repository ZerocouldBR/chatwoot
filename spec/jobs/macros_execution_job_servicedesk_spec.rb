require 'rails_helper'

# ServiceDesk M5.1: com macro_fill_editor (padrão), nem a execução em massa envia a resposta da macro.
RSpec.describe MacrosExecutionJob do
  let(:account) { create(:account) }
  let(:user) { create(:user, account: account, role: :administrator) }
  let(:conversations) { create_list(:conversation, 2, account: account, status: :open) }
  let(:macro) do
    create(:macro, account: account, actions: [
             { 'action_name' => 'send_message', 'action_params' => ['Resposta para revisar'] },
             { 'action_name' => 'add_label', 'action_params' => ['cobranca'] },
             { 'action_name' => 'set_ticket_status', 'action_params' => ['Resolvido'] }
           ])
  end

  it 'applies the actions to every conversation without sending the reply' do
    described_class.perform_now(macro, conversation_ids: conversations.map(&:display_id), user: user)

    conversations.each do |conversation|
      conversation.reload
      expect(conversation.messages.outgoing).to be_empty
      expect(conversation.label_list).to eq(['cobranca'])
      expect(conversation.custom_attributes['zd_status']).to eq('Resolvido')
      expect(conversation).to be_resolved
    end
  end

  it 'sends the reply when the account turned the setting off' do
    account.update!(macro_fill_editor: false)

    described_class.perform_now(macro, conversation_ids: [conversations.first.display_id], user: user)

    expect(conversations.first.reload.messages.outgoing.pluck(:content)).to eq(['Resposta para revisar'])
  end
end
