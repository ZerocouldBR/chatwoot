require 'rails_helper'

# ServiceDesk M4: ações set_custom_attribute, set_ticket_status e change_subject nas automações.
RSpec.describe AutomationRules::ActionService do
  let(:account) { create(:account) }
  let(:conversation) { create(:conversation, account: account, status: :open) }
  let(:conditions) do
    [{ 'attribute_key' => 'status', 'filter_operator' => 'equal_to', 'values' => ['open'], 'query_operator' => nil }]
  end

  before do
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_area_interna', attribute_display_type: 'list',
                                         attribute_values: %w[Suporte Financeiro])
    create(:custom_attribute_definition, account: account, attribute_key: 'zd_status', attribute_display_type: 'list',
                                         attribute_values: ['Novo', 'Aberto', 'Em andamento', 'Pendente', 'Resolvido'])
  end

  it 'applies the ServiceDesk actions in order' do
    rule = create(:automation_rule, account: account, event_name: 'conversation_created', conditions: conditions,
                                    actions: [
                                      { 'action_name' => 'set_custom_attribute', 'action_params' => %w[zd_area_interna Financeiro] },
                                      { 'action_name' => 'set_ticket_status', 'action_params' => ['Pendente'] },
                                      { 'action_name' => 'change_subject', 'action_params' => ['[Financeiro] Cobrança'] }
                                    ])

    described_class.new(rule, account, conversation).perform
    conversation.reload

    expect(conversation.custom_attributes).to include('zd_area_interna' => 'Financeiro', 'zd_status' => 'Pendente')
    expect(conversation.status).to eq('waiting_on_customer')
    expect(conversation.additional_attributes['mail_subject']).to eq('[Financeiro] Cobrança')
    expect(conversation.subject).to eq('[Financeiro] Cobrança')
  end

  it 'never moves the ticket to New or Closed (as in Zendesk)' do
    rule = create(:automation_rule, account: account, event_name: 'conversation_created', conditions: conditions,
                                    actions: [{ 'action_name' => 'add_label', 'action_params' => ['vip'] }])
    rule.actions = [{ 'action_name' => 'set_ticket_status', 'action_params' => ['Novo'] }]
    rule.save!(validate: false)

    described_class.new(rule, account, conversation).perform

    expect(conversation.reload.status).to eq('open')
    expect(conversation.custom_attributes['zd_status']).to be_nil
  end

  it 'keeps running the next actions when one of them is no longer valid' do
    rule = create(:automation_rule, account: account, event_name: 'conversation_created', conditions: conditions,
                                    actions: [{ 'action_name' => 'add_label', 'action_params' => ['vip'] }])
    rule.actions = [
      { 'action_name' => 'set_ticket_status', 'action_params' => ['Inventado'] },
      { 'action_name' => 'set_ticket_status', 'action_params' => ['Em andamento'] }
    ]
    rule.save!(validate: false)

    described_class.new(rule, account, conversation).perform

    expect(conversation.reload.custom_attributes['zd_status']).to eq('Em andamento')
    expect(conversation.status).to eq('open')
  end

  it 'is offered by AutomationRule#actions_attributes' do
    expect(AutomationRule.new.actions_attributes).to include('set_custom_attribute', 'set_ticket_status', 'change_subject')
  end
end
