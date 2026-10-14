require 'rails_helper'

RSpec.describe Tickets::Rules::AutomationRunner do
  let(:account) { create(:account) }
  let(:automation) do
    TicketRule.create!(account: account, kind: :automation, title: 'Lembrete',
                       conditions: { all: [{ field: 'status', operator: 'is', value: 'waiting_on_customer' },
                                           { field: 'hours_since_waiting_on_customer', operator: 'greater_than', value: '24' }], any: [] },
                       actions: [{ field: 'status', value: 'on_hold' }, { field: 'add_tags', value: 'sem_resposta' }])
  end

  it 'acts on tickets past the time condition only' do
    late = create(:conversation, account: account, status: :waiting_on_customer)
    recent = create(:conversation, account: account, status: :waiting_on_customer)
    late.update_columns(status_changed_at: 30.hours.ago) # rubocop:disable Rails/SkipsModelValidations
    recent.update_columns(status_changed_at: 2.hours.ago) # rubocop:disable Rails/SkipsModelValidations

    described_class.new(automation).perform

    expect(late.reload).to have_attributes(status: 'on_hold', label_list: ['sem_resposta'])
    expect(recent.reload.status).to eq('waiting_on_customer')
  end

  it 'requires automations to nullify themselves' do
    automation.actions = [{ field: 'add_tags', value: 'sem_resposta' }]

    expect(automation).not_to be_valid
    expect(automation.errors[:actions]).to be_present
  end

  it 'accepts an "is" hours condition instead of a nullifying action' do
    automation.conditions['all'][1]['operator'] = 'is'
    automation.actions = [{ field: 'add_tags', value: 'sem_resposta' }]

    expect(automation).to be_valid
  end
end
