require 'rails_helper'

describe Servicedesk::MessageOutboundGuard do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:email_channel) { create(:channel_email, account: account) }
  let(:conversation) { create(:conversation, account: account, inbox: email_channel.inbox) }

  def reply(**attrs)
    create(:message, account: account, inbox: conversation.inbox, conversation: conversation, sender: agent,
                     message_type: :outgoing, content: 'Resposta ao cliente', **attrs)
  end

  def blocked_events
    conversation.conversation_events.where(event_type: 'outbound_blocked')
  end

  context 'when the account is isolated' do
    before { account.update!(outbound_blocked: true) }

    it 'keeps the public reply in the ticket, marked as not sent, without the send job' do
      message = nil
      expect { message = reply }.not_to have_enqueued_job(SendReplyJob)

      expect(message.reload).to be_failed
      expect(message.outbound_blocked?).to be(true)
      expect(message.content_attributes['external_error']).to be_present
      expect(blocked_events.pluck(:field_name, :value)).to eq([['message', { 'message_id' => message.id, 'channel' => 'Channel::Email' }]])
    end

    it 'does not mark private notes nor incoming messages' do
      note = reply(private: true)
      incoming = create(:message, account: account, inbox: conversation.inbox, conversation: conversation, message_type: :incoming)

      expect(note.reload.outbound_blocked?).to be(false)
      expect(incoming.reload.outbound_blocked?).to be(false)
      expect(blocked_events).to be_empty
    end

    it 'does not send through the channel when a send job already exists' do
      message = account.update!(outbound_blocked: false) && reply
      account.update!(outbound_blocked: true)
      expect(Email::SendOnEmailService).not_to receive(:new)

      SendReplyJob.perform_now(message.id)

      expect(message.reload).to be_failed
      expect(message.outbound_blocked?).to be(true)
    end

    it 'delivers no e-mail even when the send job runs' do
      message = reply
      ActionMailer::Base.deliveries.clear

      SendReplyJob.perform_now(message.id)

      expect(ActionMailer::Base.deliveries).to be_empty
    end
  end

  context 'with SD_OUTBOUND_BLOCKED' do
    it 'marks the reply of any account' do
      with_modified_env SD_OUTBOUND_BLOCKED: 'true' do
        expect { reply }.not_to have_enqueued_job(SendReplyJob)
      end

      expect(conversation.messages.outgoing.last).to be_failed
    end
  end

  context 'when the guard is off' do
    it 'sends as before' do
      message = nil
      expect { message = reply }.to have_enqueued_job(SendReplyJob)

      expect(message.reload).to be_sent
      expect(message.outbound_blocked?).to be(false)
      expect(blocked_events).to be_empty
    end
  end
end
