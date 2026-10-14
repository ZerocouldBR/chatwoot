require 'rails_helper'

RSpec.describe Servicedesk::ConversationActionParams do
  let(:account) { create(:account) }
  let(:params) { described_class.new(account) }

  before do
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_tabulacao', attribute_display_type: 'list',
                                         attribute_values: ['Cancelamento de Reserva', 'Chargeback'])
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_vip', attribute_display_type: 'checkbox')
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_qtd', attribute_display_type: 'number')
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_data', attribute_display_type: 'date')
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_link', attribute_display_type: 'link')
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_ref', attribute_display_type: 'text',
                                         regex_pattern: '^\d+$')
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_status', attribute_display_type: 'list',
                                         attribute_values: %w[Novo Aberto Pendente Desenvolvimento Resolvido])
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_contato', attribute_display_type: 'text',
                                         attribute_model: 'contact_attribute')
  end

  describe '#custom_attribute' do
    it 'accepts a value from the list and rejects one outside it' do
      expect(params.custom_attribute('zd_tabulacao', 'Chargeback').value).to eq('Chargeback')
      expect(params.custom_attribute('zd_tabulacao', 'Outra').error).to include('fora da lista')
    end

    it 'casts checkbox values' do
      expect(params.custom_attribute('zd_vip', 'true').value).to be(true)
      expect(params.custom_attribute('zd_vip', 'false').value).to be(false)
      expect(params.custom_attribute('zd_vip', 'talvez').error).to be_present
    end

    it 'casts number and date values' do
      expect(params.custom_attribute('zd_qtd', '42').value).to eq(42)
      expect(params.custom_attribute('zd_qtd', '4.5').value).to eq(4.5)
      expect(params.custom_attribute('zd_qtd', 'muitos').error).to be_present
      expect(params.custom_attribute('zd_data', '2026-10-13').value).to eq('2026-10-13')
      expect(params.custom_attribute('zd_data', '13/10/2026').error).to be_present
    end

    it 'validates links and the text regex' do
      expect(params.custom_attribute('zd_link', 'https://exemplo.test/x').ok?).to be(true)
      expect(params.custom_attribute('zd_link', 'javascript:alert(1)').error).to be_present
      expect(params.custom_attribute('zd_ref', '123').value).to eq('123')
      expect(params.custom_attribute('zd_ref', 'abc').error).to include('formato')
    end

    it 'clears the attribute with a blank value' do
      result = params.custom_attribute('zd_tabulacao', '')

      expect(result.ok?).to be(true)
      expect(result.value).to be_nil
    end

    it 'only accepts conversation attributes and refuses zd_status' do
      expect(params.custom_attribute('zd_contato', 'x').error).to include('inexistente')
      expect(params.custom_attribute('nao_existe', 'x').error).to include('inexistente')
      expect(params.custom_attribute('zd_status', 'Aberto').error).to include('set_ticket_status')
    end
  end

  describe '#ticket_status' do
    it 'accepts a known label that is in the account list' do
      expect(params.ticket_status('Desenvolvimento').value['category']).to eq('hold')
    end

    it 'rejects an unknown label and a label missing from the account list' do
      expect(params.ticket_status('Inventado').error).to include('desconhecido')
      expect(params.ticket_status('Escalonado').error).to include('fora da lista')
    end
  end

  describe '#subject' do
    it 'squishes the subject and limits its size' do
      expect(params.subject("  Novo   assunto \n").value).to eq('Novo assunto')
      expect(params.subject(' ').error).to be_present
      expect(params.subject('a' * 501).error).to be_present
    end
  end

  describe '#errors_for' do
    it 'checks the params of each ServiceDesk action and ignores the others' do
      errors = params.errors_for([
                                   { 'action_name' => 'set_custom_attribute', 'action_params' => ['zd_tabulacao'] },
                                   { 'action_name' => 'set_ticket_status', 'action_params' => [{ 'label' => 'Novo' }] },
                                   { 'action_name' => 'change_subject', 'action_params' => ['Ok'] },
                                   { action_name: :set_ticket_status, action_params: ['Inventado'] },
                                   { 'action_name' => 'add_label', 'action_params' => [] }
                                 ])

      expect(errors).to eq([
                             'set_custom_attribute: parâmetros esperados: [chave, valor]',
                             'set_ticket_status: parâmetro esperado: [rótulo do status]',
                             'set_ticket_status: status desconhecido: Inventado'
                           ])
    end
  end
end
