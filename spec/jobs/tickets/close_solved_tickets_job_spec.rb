require 'rails_helper'

RSpec.describe Tickets::CloseSolvedTicketsJob do
  let(:account) { create(:account) }
  let!(:old_solved) { create(:conversation, account: account, status: :resolved) }
  let!(:recent_solved) { create(:conversation, account: account, status: :resolved) }
  let!(:old_open) { create(:conversation, account: account, status: :open) }

  before do
    old_solved.update_columns(status_changed_at: 97.hours.ago) # rubocop:disable Rails/SkipsModelValidations
    recent_solved.update_columns(status_changed_at: 95.hours.ago) # rubocop:disable Rails/SkipsModelValidations
    old_open.update_columns(status_changed_at: 30.days.ago) # rubocop:disable Rails/SkipsModelValidations
  end

  it 'closes tickets solved for longer than the default 96 hours' do
    described_class.perform_now

    expect([old_solved, recent_solved, old_open].map { |ticket| ticket.reload.status }).to eq(%w[closed resolved open])
  end

  it 'uses the close delay configured on the account' do
    account.update!(close_solved_after_hours: 24)

    described_class.perform_now

    expect(recent_solved.reload.status).to eq('closed')
  end

  it 'records the closing as a system change' do
    described_class.perform_now

    expect(old_solved.conversation_events.last).to have_attributes(field_name: 'status', value: 'closed', via: 'system')
  end
end
