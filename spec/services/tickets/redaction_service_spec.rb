require 'rails_helper'

RSpec.describe Tickets::RedactionService do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :administrator) }
  let(:conversation) { create(:conversation, account: account) }
  let(:message) do
    create(:message, conversation: conversation, account: account, inbox: conversation.inbox, content: 'Cartão 4111 1111 1111 1111 recusado',
                     content_attributes: { email: { text_content: { full: 'Cartão 4111 1111 1111 1111 recusado' } } })
  end

  it 'replaces the text everywhere in the message, tags the ticket and records the redaction' do
    described_class.new(message: message, user: agent, text: '4111 1111 1111 1111').perform

    expect(message.reload.content).to eq("Cartão #{'▇' * 19} recusado")
    expect(message.content_attributes.dig('email', 'text_content', 'full')).not_to include('4111')
    expect(conversation.reload.label_list).to include('redacted_content')
    expect(conversation.conversation_events.last).to have_attributes(event_type: 'redaction', via: 'agent')
  end

  it 'redacts the whole comment without text' do
    described_class.new(message: message, user: agent).perform

    expect(message.reload.content).to match(/\A▇+\z/)
  end
end
