require 'rails_helper'

RSpec.describe Tickets::CcList do
  let(:account) { create(:account) }
  let(:channel) { create(:channel_email, account: account, email: 'suporte@example.com') }
  let(:contact) { create(:contact, account: account, email: 'cliente@example.com') }
  let(:conversation) { create(:conversation, account: account, inbox: channel.inbox, contact: contact) }
  let(:cc_list) { described_class.new(conversation) }

  it 'adds new CCs without the requester, the support address or duplicates' do
    cc_list.add(['Gerente@Example.com', 'cliente@example.com', 'suporte@example.com', 'gerente@example.com', 'invalid'],
                author: nil, via: 'agent')

    expect(cc_list.emails).to eq(['gerente@example.com'])
  end

  it 'keeps at most 48 CCs' do
    cc_list.add((1..50).map { |i| "cc#{i}@example.com" }, author: nil, via: 'agent')

    expect(cc_list.emails.size).to eq(48)
  end

  it 'records CC changes in the ticket events' do
    cc_list.add(['gerente@example.com'], author: nil, via: 'agent')
    cc_list.remove('gerente@example.com', author: nil, via: 'agent')

    changes = conversation.conversation_events.where(field_name: 'ccs').order(:id).pluck(:previous_value, :value)
    expect(changes).to eq([[[], ['gerente@example.com']], [['gerente@example.com'], []]])
  end
end
