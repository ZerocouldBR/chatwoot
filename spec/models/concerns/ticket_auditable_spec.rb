require 'rails_helper'

RSpec.describe TicketAuditable do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:conversation) { create(:conversation, account: account) }

  after { Current.reset }

  it 'records the ticket creation with its initial fields' do
    event = conversation.conversation_events.find_by(event_type: 'create')

    expect(event).to have_attributes(via: 'system')
    expect(event.value).to include('status' => 'open')
  end

  it 'records each changed ticket field with the agent who changed it' do
    Current.user = agent

    conversation.update!(status: :on_hold, priority: :high)

    changes = conversation.conversation_events.where(event_type: 'change').pluck(:field_name, :previous_value, :value, :via, :author_id)
    expect(changes).to contain_exactly(['status', 'open', 'on_hold', 'agent', agent.id], ['priority', nil, 'high', 'agent', agent.id])
  end

  it 'attributes changes made by a ticket rule to the rule' do
    rule = TicketRule.create!(account: account, kind: :trigger, title: 'Urgente',
                              conditions: { all: [{ field: 'ticket', operator: 'is', value: 'created' }], any: [] },
                              actions: [{ field: 'priority', value: 'urgent' }])
    Current.executed_by = rule

    conversation.update!(priority: :urgent)

    expect(conversation.conversation_events.last).to have_attributes(via: 'rule', author: rule)
  end

  it 'records public replies and private notes as comments' do
    create(:message, conversation: conversation, account: account, inbox: conversation.inbox, message_type: :incoming,
                     sender: conversation.contact)
    create(:message, conversation: conversation, account: account, inbox: conversation.inbox, message_type: :outgoing,
                     sender: agent, private: true)

    comments = conversation.conversation_events.where(event_type: 'comment').order(:id)
    expect(comments.map(&:via)).to eq(%w[customer agent])
    expect(comments.map { |event| event.value['public'] }).to eq([true, false])
  end

  it 'never updates an existing event' do
    event = conversation.conversation_events.first

    expect { event.update!(via: 'agent') }.to raise_error(ActiveRecord::ReadOnlyRecord)
  end
end
