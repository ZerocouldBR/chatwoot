require 'rails_helper'

RSpec.describe Sla::Applier do
  let(:account) { create(:account) }
  let(:conversation) { create(:conversation, account: account, status: :open, priority: :high, label_list: ['vip']) }
  let(:frt_one_hour) { [{ 'metric' => 'first_reply_time', 'priority' => 'high', 'minutes' => 60, 'business_hours' => false }] }

  def policy(name, position, filter = {})
    SlaPolicy.create!(account: account, name: name, position: position, filter: filter, targets: frt_one_hour)
  end

  it 'applies the first matching policy by position' do
    policy('Geral', 2)
    vip = policy('VIP', 1, { 'all' => [{ 'field' => 'labels', 'operator' => 'includes', 'value' => 'vip' }] })

    described_class.new(conversation).perform

    expect(conversation.reload.sla_policy_id).to eq(vip.id)
    expect(conversation.next_sla_breach_at).to be_within(1.minute).of(conversation.created_at + 1.hour)
  end

  it 'does not apply an SLA to tickets without priority' do
    policy('Geral', 1)
    conversation.update_columns(priority: nil) # rubocop:disable Rails/SkipsModelValidations

    described_class.new(conversation).perform

    expect(AppliedSla.where(conversation: conversation)).to be_empty
  end

  it 'records the breach once and flags the ticket' do
    policy('Geral', 1)

    described_class.new(conversation).perform(now: conversation.created_at + 2.hours)
    described_class.new(conversation).perform(now: conversation.created_at + 3.hours)

    expect(conversation.reload.sla_breached).to be(true)
    expect(SlaEvent.where(conversation: conversation, event_type: :breach).count).to eq(1)
    expect(conversation.applied_sla).to be_missed
  end

  it 'notifies the assignee when the first reply target is missed' do
    agent = create(:user, account: account, role: :agent)
    create(:inbox_member, inbox: conversation.inbox, user: agent)
    conversation.update!(assignee: agent)
    policy('Geral', 1)

    expect { described_class.new(conversation).perform(now: conversation.created_at + 2.hours) }
      .to change { Notification.where(user: agent, notification_type: 'sla_missed_first_response').count }.by(1)
  end

  it 'removes the SLA when no policy matches anymore' do
    policy('VIP', 1, { 'all' => [{ 'field' => 'labels', 'operator' => 'includes', 'value' => 'vip' }] })
    described_class.new(conversation).perform

    conversation.update!(label_list: [])
    described_class.new(conversation).perform

    expect(conversation.reload.sla_policy_id).to be_nil
  end

  it 'refuses business-hours targets without a default schedule' do
    business = frt_one_hour.map { |target| target.merge('business_hours' => true) }

    expect(SlaPolicy.new(account: account, name: 'X', targets: business)).not_to be_valid
  end
end
