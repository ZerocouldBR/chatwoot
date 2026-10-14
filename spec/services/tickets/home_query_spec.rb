require 'rails_helper'

RSpec.describe Tickets::HomeQuery do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :administrator, email: 'agente@example.com') }
  let(:query) { described_class.new(account: account, user: agent) }
  let!(:mine) { create(:conversation, account: account, assignee: agent, status: :open) }
  let!(:copied) { create(:conversation, account: account, status: :waiting_on_customer) }
  let!(:followed) { create(:conversation, account: account, status: :on_hold) }
  let!(:solved) { create(:conversation, account: account, assignee: agent, status: :resolved) }

  before do
    create(:conversation, account: account, assignee: agent, status: :resolved).tap do |old|
      old.update_columns(status_changed_at: 31.days.ago) # rubocop:disable Rails/SkipsModelValidations
    end
    ConversationCc.create!(account: account, conversation: copied, email: 'Agente@example.com')
    create(:conversation_participant, conversation: followed, user: agent)
  end

  it 'lists each home view' do
    expect(query.tickets('mine')).to contain_exactly(mine)
    expect(query.tickets('ccs')).to contain_exactly(copied)
    expect(query.tickets('following')).to contain_exactly(followed)
    expect(query.tickets('solved')).to contain_exactly(solved)
  end

  it 'counts every view' do
    expect(query.counts).to eq('mine' => 1, 'ccs' => 1, 'following' => 1, 'solved' => 1)
  end
end
