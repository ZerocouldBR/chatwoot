require 'rails_helper'

RSpec.describe Tickets::Rules::TriggerRunner do
  let(:account) { create(:account) }
  let(:conversation) { create(:conversation, account: account, priority: nil) }
  let(:trigger) do
    lambda do |title, position, conditions, actions|
      TicketRule.create!(account: account, kind: :trigger, title: title, position: position,
                         conditions: { all: conditions, any: [] }, actions: actions)
    end
  end

  it 'fires matching triggers on the creation update and restarts the list after each one' do
    trigger.call('VIP', 1, [{ field: 'priority', operator: 'changed_to', value: 'medium' }], [{ field: 'add_tags', value: 'vip' }])
    trigger.call('Normal', 2, [{ field: 'ticket', operator: 'is', value: 'created' }, { field: 'priority', operator: 'is', value: '' }],
                 [{ field: 'priority', value: 'medium' }])

    described_class.new(conversation).perform

    expect(conversation.reload.priority).to eq('medium')
    expect(conversation.label_list).to eq(['vip'])
    expect(conversation.conversation_events.where(via: 'rule').pluck(:field_name)).to contain_exactly('priority', 'cached_label_list')
  end

  it 'evaluates each update once and ignores the changes made by its own triggers afterwards' do
    trigger.call('Tag on update', 1, [{ field: 'ticket', operator: 'is', value: 'updated' }], [{ field: 'add_tags', value: 'seen' }])
    described_class.new(conversation).perform
    expect(conversation.reload.label_list).to be_empty

    conversation.update!(status: :on_hold)
    described_class.new(conversation).perform
    described_class.new(conversation.reload).perform

    expect(conversation.reload.label_list).to eq(['seen'])
    expect(conversation.conversation_events.where(via: 'rule').count).to eq(1)
  end

  it 'e-mails the requester with placeholders after the triggers ran' do
    conversation.contact.update!(email: 'cliente@example.com')
    trigger.call('Recebido', 1, [{ field: 'ticket', operator: 'is', value: 'created' }],
                 [{ field: 'email_requester', value: { subject: 'Pedido #{{ticket.id}}', body: 'Status: {{ticket.status}}' } }])

    expect { described_class.new(conversation).perform }
      .to have_enqueued_mail(TicketRequesterMailer, :ticket_notification)
      .with(a_hash_including(params: { account: account }, args: [conversation, a_hash_including(subject: "Pedido ##{conversation.display_id}")]))
  end

  it 'skips closed tickets' do
    trigger.call('Normal', 1, [{ field: 'ticket', operator: 'is', value: 'updated' }], [{ field: 'priority', value: 'high' }])
    conversation.update!(status: :resolved)
    conversation.update!(status: :closed)

    described_class.new(conversation).perform

    expect(conversation.reload.priority).to be_nil
  end
end
