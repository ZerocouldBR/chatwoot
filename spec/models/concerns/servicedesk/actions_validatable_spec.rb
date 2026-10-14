require 'rails_helper'

RSpec.describe Servicedesk::ActionsValidatable do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:valid_actions) do
    [
      { 'action_name' => 'set_custom_attribute', 'action_params' => %w[zd_tabulacao Chargeback] },
      { 'action_name' => 'set_ticket_status', 'action_params' => ['Desenvolvimento'] },
      { 'action_name' => 'change_subject', 'action_params' => ['Reserva 123'] }
    ]
  end
  let(:invalid_actions) do
    [
      { 'action_name' => 'set_custom_attribute', 'action_params' => %w[zd_tabulacao Outra] },
      { 'action_name' => 'set_ticket_status', 'action_params' => ['Inventado'] }
    ]
  end

  before do
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_tabulacao', attribute_display_type: 'list',
                                         attribute_values: ['Chargeback'])
  end

  describe 'Macro' do
    it 'accepts the ServiceDesk actions with valid params' do
      macro = build(:macro, account: account, created_by: admin, updated_by: admin, actions: valid_actions)

      expect(macro).to be_valid
    end

    it 'rejects invalid params' do
      macro = build(:macro, account: account, created_by: admin, updated_by: admin, actions: invalid_actions)

      expect(macro).not_to be_valid
      expect(macro.errors[:actions]).to include('set_custom_attribute: valor fora da lista de zd_tabulacao: Outra',
                                                'set_ticket_status: status desconhecido: Inventado')
    end
  end
end
