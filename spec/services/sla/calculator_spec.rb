require 'rails_helper'

RSpec.describe Sla::Calculator do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:contact) { create(:contact, account: account) }
  let(:inbox) { create(:inbox, account: account) }
  let(:start) { Time.zone.parse('2026-10-12 10:00:00 UTC') }
  let(:targets) do
    { 'first_reply_time' => 60, 'next_reply_time' => 30, 'requester_wait_time' => 120, 'agent_work_time' => 60,
      'total_resolution_time' => 240, 'periodic_update' => 60, 'pausable_update' => 60 }
  end
  let(:policy) do
    create_policy(targets.map { |metric, minutes| { 'metric' => metric, 'priority' => 'urgent', 'minutes' => minutes, 'business_hours' => false } })
  end
  let(:conversation) do
    travel_to(start) do
      create(:conversation, account: account, inbox: inbox, contact: contact, status: :new_ticket, priority: :urgent).tap do |ticket|
        reply_from(:customer, ticket)
      end
    end
  end

  before { conversation }

  def create_policy(policy_targets)
    SlaPolicy.create!(account: account, name: 'Urgentes', targets: policy_targets)
  end

  def reply_from(who, ticket = conversation)
    sender = who == :customer ? ticket.contact : agent
    create(:message, conversation: ticket, account: account, inbox: inbox, sender: sender,
                     message_type: who == :customer ? :incoming : :outgoing)
  end

  def at(minutes, &)
    travel_to(start + minutes.minutes, &)
  end

  def metrics_at(minutes, schedule: nil)
    described_class.new(conversation: conversation.reload, policy: policy, schedule: schedule, now: start + minutes.minutes).metrics
  end

  it 'fulfils the first reply time at the first public agent reply' do
    at(30) { reply_from(:agent) }

    expect(metrics_at(40)['first_reply_time']).to include('status' => 'fulfilled', 'elapsed_seconds' => 30.minutes.to_i, 'breached' => false)
  end

  it 'breaches the first reply time when nobody answers in time' do
    state = metrics_at(61)['first_reply_time']

    expect(state).to include('status' => 'active', 'breached' => true, 'breach_at' => nil)
  end

  it 'points to the breach time while a target is running' do
    expect(metrics_at(15)['first_reply_time']['breach_at']).to eq((start + 60.minutes).iso8601)
  end

  it 'pauses requester wait and agent work while Pending, but not total resolution' do
    at(30) { conversation.update!(status: :waiting_on_customer) }
    metrics = metrics_at(90)

    expect(metrics['requester_wait_time']).to include('status' => 'paused', 'elapsed_seconds' => 30.minutes.to_i)
    expect(metrics['agent_work_time']).to include('status' => 'paused', 'elapsed_seconds' => 30.minutes.to_i)
    expect(metrics['total_resolution_time']).to include('status' => 'active', 'elapsed_seconds' => 90.minutes.to_i)
  end

  it 'pauses only agent work while On-hold' do
    at(30) { conversation.update!(status: :on_hold) }
    metrics = metrics_at(90)

    expect(metrics['agent_work_time']['elapsed_seconds']).to eq(30.minutes.to_i)
    expect(metrics['requester_wait_time']['elapsed_seconds']).to eq(90.minutes.to_i)
  end

  it 'starts next reply time at the customer comment after an agent reply' do
    at(10) { reply_from(:agent) }
    at(20) { reply_from(:customer) }

    expect(metrics_at(60)['next_reply_time']).to include('status' => 'active', 'elapsed_seconds' => 40.minutes.to_i, 'breached' => true)
  end

  it 'stops every metric when the ticket is solved' do
    at(10) { reply_from(:agent) }
    at(50) { conversation.update!(status: :resolved, assignee: agent) }

    metrics = metrics_at(500)
    expect(metrics.values_at('total_resolution_time', 'agent_work_time').pluck('status')).to all(eq('fulfilled'))
    expect(metrics['total_resolution_time']['elapsed_seconds']).to eq(50.minutes.to_i)
  end

  it 'counts business hours only when the target says so' do
    zone = ActiveSupport::TimeZone['America/Sao_Paulo']
    schedule = BusinessSchedule.create!(account: account, name: 'Comercial', time_zone: 'America/Sao_Paulo', is_default: true,
                                        intervals: (1..5).map { |day| { 'day' => day, 'start' => 540, 'end' => 1080 } })
    friday_evening = zone.local(2026, 10, 16, 17, 30)
    policy.update!(targets: [{ 'metric' => 'first_reply_time', 'priority' => 'urgent', 'minutes' => 60, 'business_hours' => true }])
    ticket = travel_to(friday_evening) { create(:conversation, account: account, inbox: inbox, contact: contact, priority: :urgent) }

    state = described_class.new(conversation: ticket, policy: policy, schedule: schedule, now: friday_evening + 1.minute).metrics['first_reply_time']

    expect(state['breach_at']).to eq(zone.local(2026, 10, 19, 9, 30).iso8601)
  end
end
