require 'rails_helper'

RSpec.describe Conversations::DeleteService do
  let(:account) { create(:account) }
  let(:user) { create(:user, account: account) }
  let(:ip) { '127.0.0.1' }
  let(:service) { described_class.new(conversation: conversation, user: user, ip: ip) }

  context 'when deleting an email conversation' do
    let(:inbox) { create(:channel_email, :imap_email, account: account).inbox }
    let(:conversation) { create(:conversation, account: account, inbox: inbox) }
    let!(:incoming_message) { create(:message, account: account, inbox: inbox, conversation: conversation, source_id: 'incoming@example.com') }
    let(:deleted_message_tracker) { instance_double(Imap::DeletedMessageTracker, record: true) }

    before do
      allow(Imap::DeletedMessageTracker).to receive(:new).with(inbox: inbox).and_return(deleted_message_tracker)
    end

    it 'records incoming message source ids and moves the ticket to the trash' do
      service.perform

      expect(Conversation.trashed.find(conversation.id)).to be_present

      expect(deleted_message_tracker).to have_received(:record).with([incoming_message.source_id])
    end
  end

  context 'when deleting a non-email conversation' do
    let(:conversation) { create(:conversation, account: account) }

    it 'moves the ticket to the trash without recording message source ids' do
      expect(Imap::DeletedMessageTracker).not_to receive(:new)

      service.perform

      expect(Conversation.trashed.find(conversation.id)).to be_present
    end
  end
end
