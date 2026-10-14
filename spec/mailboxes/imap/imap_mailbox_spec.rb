require 'rails_helper'

RSpec.describe Imap::ImapMailbox do
  include ActionMailbox::TestHelper

  describe '#process' do
    let(:account) { create(:account) }
    let(:agent) { create(:user, email: 'agent@example.com', account: account) }
    let(:channel) { create(:channel_email, :imap_email) }
    let(:inbox) { channel.inbox }
    let!(:contact) { create(:contact, email: 'email@gmail.com', phone_number: '+919584546666', account: account, identifier: '123') }
    let(:conversation) { Conversation.where(inbox_id: channel.inbox).last }
    let(:class_instance) { described_class.new }

    before do
      create(:contact_inbox, contact_id: contact.id, inbox_id: channel.inbox.id)
    end

    context 'when the email is from a new contact' do
      let(:inbound_mail) { create_inbound_email_from_mail(from: 'testemail@gmail.com', to: 'imap@gmail.com', subject: 'Hello!') }

      it 'creates the contact and conversation with message' do
        expect do
          class_instance.process(inbound_mail.mail, channel)
        end.to change(Conversation, :count).by(1)

        expect(conversation.contact.email).to eq(inbound_mail.mail.from.first)
        expect(conversation.additional_attributes['source']).to eq('email')
        expect(conversation.messages.empty?).to be false
      end
    end

    context 'when reply-to contains an empty quoted address' do
      let(:inbound_mail) { create_inbound_email_from_fixture('malformed_reply_to.eml') }
      let(:mail) { inbound_mail.mail }

      it 'creates a conversation and message using the valid from address' do
        expect(mail.reply_to).to eq([nil])

        expect do
          class_instance.process(mail, channel)
        end.to change(Conversation, :count).by(1).and change(Message, :count).by(1)

        expect(conversation.contact.email).to eq('sender@example.com')
        expect(conversation.messages.last.content_attributes.dig('email', 'from')).to eq(['sender@example.com'])
      end
    end

    context 'when the email with has empty text content' do
      let(:inbound_mail) { create_inbound_email_from_fixture('attachments_without_text.eml') }

      it 'creates a converstation and a message properly' do
        expect do
          class_instance.process(inbound_mail.mail, channel)
        end.to change(Conversation, :count).by(1)

        expect(conversation.contact.email).to eq(inbound_mail.mail.from.first)
        expect(conversation.messages.last.attachments.count).to be 2
      end
    end

    context 'when the email has attachments with no filename' do
      let(:inbound_mail) { create_inbound_email_from_fixture('attachments_without_filename.eml') }

      it 'creates a conversation and a message with properly named attachments' do
        expect do
          class_instance.process(inbound_mail.mail, channel)
        end.to change(Conversation, :count).by(1)

        last_message = conversation.messages.last
        expect(last_message.attachments.count).to be 2

        filenames = last_message.attachments.map(&:file).map { |file| file.blob.filename.to_s }
        expect(filenames.all? { |filename| filename.present? && filename.start_with?('attachment_') }).to be true
      end
    end

    context 'when the email has inline attachments other than images' do
      let(:inbound_mail) { create_inbound_email_from_fixture('email_with_inline_pdf.eml') }

      it 'creates a conversation and a message with non-image files as regular attachments' do
        expect do
          class_instance.process(inbound_mail.mail, channel)
        end.to change(Conversation, :count).by(1)

        last_message = conversation.messages.last
        expect(last_message.attachments.count).to be 1

        attachment = last_message.attachments.first
        expect(attachment.file.blob.filename.to_s).to eq 'dummy.pdf'
      end
    end

    context 'when the email has 15 or more attachments' do
      let(:inbound_mail) { create_inbound_email_from_fixture('multiple_attachments.eml') }

      it 'creates a converstation and a message properly' do
        expect do
          class_instance.process(inbound_mail.mail, channel)
        end.to change(Conversation, :count).by(1)

        expect(conversation.contact.email).to eq(inbound_mail.mail.from.first)
        expect(conversation.messages.last.attachments.count).to be 15
      end
    end

    context 'when a new email from existing contact' do
      let(:inbound_mail) { create_inbound_email_from_mail(from: 'email@gmail.com', to: 'imap@gmail.com', subject: 'Hello!') }

      it 'creates a new conversation with message' do
        class_instance.process(inbound_mail.mail, channel)
        expect(conversation.contact.email).to eq(contact.email)
        expect(conversation.additional_attributes['source']).to eq('email')
        expect(conversation.messages.empty?).to be false
      end
    end

    context 'when a new email contains null bytes' do
      let(:inbound_mail) do
        Mail.new.tap do |mail|
          mail.from = 'email@gmail.com'
          mail.to = 'imap@gmail.com'
          mail.subject = "Hello\u0000"
          mail.message_id = "message\u0000@example.com"
          mail['In-Reply-To'] = "source\u0000@example.com"
          mail.references = ["reference\u0000@example.com"]
          mail.content_type = 'text/plain'
          mail.body = "Body\u0000 text"
        end
      end

      it 'creates sanitized conversation and message records' do
        expect { class_instance.process(inbound_mail, channel) }.to change(Conversation, :count).by(1)

        message = conversation.messages.last

        expect(conversation.additional_attributes['in_reply_to']).to eq('source@example.com')
        expect(conversation.additional_attributes['mail_subject']).to eq('Hello')
        expect(message.source_id).to eq('message@example.com')
        expect(message.content).to eq('Body text')
        expect(message.content_attributes.to_json).not_to include('\u0000')
      end
    end

    context 'when a new email with invalid from' do
      let(:inbound_mail) { create_inbound_email_from_mail(from: 'invalidemail', to: 'imap@gmail.com', subject: 'Hello!') }

      it 'does not create a new conversation' do
        expect { class_instance.process(inbound_mail.mail, channel) }.not_to raise_error
      end
    end

    context 'when the email copies other people' do
      let(:inbound_mail) do
        create_inbound_email_from_mail(from: 'email@gmail.com', to: [channel.email, 'diretor@example.com'], cc: 'gerente@example.com',
                                       subject: 'Reserva com cópia')
      end

      it 'adds the copied people as ticket CCs' do
        class_instance.process(inbound_mail.mail, channel)

        expect(Tickets::CcList.new(conversation).emails).to contain_exactly('diretor@example.com', 'gerente@example.com')
      end
    end

    context 'when a CC replies on the thread' do
      let(:ticket) { create(:conversation, account: account, inbox: channel.inbox, contact: contact) }
      let(:reply_mail) do
        create_inbound_email_from_mail(from: 'gerente@example.com', to: channel.email, subject: 'Re: Reserva', in_reply_to: 'agent-reply-id')
      end

      before do
        create(:message, message_type: 'outgoing', inbox: inbox, account: account, conversation: ticket, source_id: 'agent-reply-id')
      end

      it 'adds the reply to the same ticket as written by the CC' do
        class_instance.process(reply_mail.mail, channel)

        expect(ticket.messages.incoming.last.sender.email).to eq('gerente@example.com')
        expect(Tickets::CcList.new(ticket).emails).to eq(['gerente@example.com'])
      end
    end

    context 'when the email was sent from the support address itself' do
      let(:inbound_mail) { create_inbound_email_from_mail(from: channel.email, to: 'cliente@example.com', subject: 'Re: Hello!') }

      it 'ignores it instead of adding it to a ticket' do
        expect { class_instance.process(inbound_mail.mail, channel) }.not_to change(Conversation, :count)
        expect(Message.where(inbox: channel.inbox)).to be_empty
      end
    end

    context 'when an auto reply email' do
      let(:auto_reply_mail) { create_inbound_email_from_fixture('auto_reply.eml') }

      it 'holds it as a suspended ticket instead of creating a ticket' do
        expect { class_instance.process(auto_reply_mail.mail, channel) }.not_to change(Conversation, :count)
        expect(SuspendedTicket.last).to have_attributes(reason: 'automated_response', inbox_id: channel.inbox.id)
        expect(SuspendedTicket.last.raw_email).to be_attached
      end
    end

    context 'when the sender is blocked' do
      let(:inbound_mail) { create_inbound_email_from_mail(from: 'blocked@example.com', to: 'imap@gmail.com', subject: 'Spam!') }

      before { create(:contact, email: 'blocked@example.com', account: channel.account, blocked: true) }

      it 'holds the e-mail and creates the ticket once an agent recovers it' do
        expect { class_instance.process(inbound_mail.mail, channel) }.not_to change(Conversation, :count)
        held = SuspendedTicket.last
        expect(held).to have_attributes(reason: 'blocked_sender', from_email: 'blocked@example.com', subject: 'Spam!')

        expect { held.recover! }.to change(Conversation, :count).by(1)
        expect(held.reload.recovered_at).to be_present
      end
    end

    context 'when the email is bounced' do
      let!(:bounced_mail) { create_inbound_email_from_fixture('bounced_gmail.eml') }

      it 'processes the bounced email' do
        expect { class_instance.process(bounced_mail.mail, channel) }.to change(Message, :count)
        expect(Message.last.content_attributes['email']['auto_reply']).to be true
        expect(Conversation.last.additional_attributes['auto_reply']).to be true
      end
    end

    context 'when a reply for existing email conversation' do
      let(:prev_conversation) { create(:conversation, account: account, inbox: channel.inbox, assignee: agent) }
      let(:reply_mail) do
        create_inbound_email_from_mail(from: 'email@gmail.com', to: 'imap@gmail.com', subject: 'Hello!', in_reply_to: 'test-in-reply-to')
      end

      it 'appends new email to the existing conversation' do
        create(
          :message,
          content: 'Incoming Message',
          message_type: 'incoming',
          inbox: inbox,
          account: account,
          conversation: prev_conversation
        )
        create(
          :message,
          content: 'Outgoing Message',
          message_type: 'outgoing',
          inbox: inbox,
          source_id: 'test-in-reply-to',
          account: account,
          conversation: prev_conversation
        )

        expect(prev_conversation.messages.size).to eq(2)

        class_instance.process(reply_mail.mail, channel)

        expect(prev_conversation.messages.size).to eq(3)
        expect(prev_conversation.messages.last.content_attributes['email']['from']).to eq(reply_mail.mail.from)
        expect(prev_conversation.messages.last.content_attributes['email']['to']).to eq(reply_mail.mail.to)
        expect(prev_conversation.messages.last.content_attributes['email']['subject']).to eq(reply_mail.mail.subject)
        expect(prev_conversation.messages.last.content_attributes['email']['in_reply_to']).to eq(reply_mail.mail.in_reply_to)
      end
    end

    context 'when a reply arrives for a closed ticket' do
      let(:closed_ticket) do
        create(:conversation, account: account, inbox: channel.inbox, contact: contact, assignee: agent, priority: :high,
                              subject: 'Cartão recusado', label_list: ['vip'])
      end
      let(:reply_mail) do
        create_inbound_email_from_mail(from: 'email@gmail.com', to: 'imap@gmail.com', subject: 'Re: Cartão recusado', in_reply_to: 'closed-reply-id')
      end

      before do
        create(:message, message_type: 'outgoing', inbox: inbox, account: account, conversation: closed_ticket, source_id: 'closed-reply-id')
        closed_ticket.update!(status: :closed)
      end

      it 'opens a follow-up ticket linked to the closed one' do
        expect { class_instance.process(reply_mail.mail, channel) }.to change(Conversation, :count).by(1)

        followup = Conversation.order(:id).last
        expect(followup).to have_attributes(followup_source_id: closed_ticket.id, status: 'new_ticket', subject: 'Cartão recusado',
                                            contact_id: contact.id, priority: nil, assignee_id: nil)
        expect(followup.label_list).to eq(['vip'])
        expect(followup.messages.last.content_attributes['email']['in_reply_to']).to eq('closed-reply-id')
        expect(closed_ticket.reload.status).to eq('closed')
        expect(closed_ticket.messages.count).to eq(1)
      end
    end

    context 'when a reply to a forwarded email' do
      let(:prev_conversation) { create(:conversation, account: account, inbox: channel.inbox, assignee: agent) }
      let(:supplier_reply) do
        create_inbound_email_from_mail(from: 'supplier@example.com', to: 'imap@gmail.com', subject: 'Re: Fwd: Hello!',
                                       in_reply_to: '<forward/1@example.com>')
      end

      before do
        create(:message, conversation: prev_conversation, account: account, inbox: inbox, message_type: :outgoing,
                         source_id: 'forward/1@example.com', content_attributes: { forwarded_message_id: 1, to_emails: ['supplier@example.com'] })
      end

      it 'starts a new conversation with the forward recipient instead of using the original conversation' do
        expect { class_instance.process(supplier_reply.mail, channel) }.to change(Conversation, :count).by(1)

        expect(prev_conversation.messages.incoming).to be_empty
        expect(conversation.contact.email).to eq('supplier@example.com')
      end

      it 'keeps further replies from the same recipient in their conversation' do
        class_instance.process(supplier_reply.mail, channel)
        second_reply = create_inbound_email_from_mail(from: 'supplier@example.com', to: 'imap@gmail.com', subject: 'Re: Fwd: Hello!',
                                                      in_reply_to: '<forward/1@example.com>')

        expect { class_instance.process(second_reply.mail, channel) }.not_to change(Conversation, :count)
        expect(conversation.messages.incoming.count).to eq(2)
      end
    end

    context 'when a new conversation with nil in_reply_to' do
      let(:prev_conversation) { create(:conversation, account: account, inbox: channel.inbox, assignee: agent) }
      let(:reply_mail) do
        create_inbound_email_from_mail(from: 'email@gmail.com', to: 'imap@gmail.com', subject: 'Hello!', in_reply_to: nil)
      end

      it 'appends new email to the existing conversation' do
        create(
          :message,
          content: 'Incoming Message',
          message_type: 'incoming',
          inbox: inbox,
          account: account,
          conversation: prev_conversation
        )
        create(
          :message,
          content: 'Outgoing Message',
          message_type: 'outgoing',
          inbox: inbox,
          source_id: nil,
          account: account,
          conversation: prev_conversation
        )

        expect(prev_conversation.messages.size).to eq(2)

        class_instance.process(reply_mail.mail, channel)

        expect(prev_conversation.messages.size).to eq(2)

        new_converstion_message = Conversation.last.messages.last.content_attributes
        expect(new_converstion_message['email']['subject']).to eq('Hello!')
      end
    end

    context 'when a reply for non existing email conversation' do
      let(:reply_mail) do
        create_inbound_email_from_mail(from: 'email@gmail.com', to: 'imap@gmail.com', subject: 'Hello!', in_reply_to: 'test-in-reply-to')
      end
      let(:references_email) { create_inbound_email_from_fixture('references.eml') }

      it 'creates new email conversation with incoming in-reply-to' do
        class_instance.process(reply_mail.mail, channel)
        expect(conversation.additional_attributes['in_reply_to']).to eq(reply_mail.mail.in_reply_to)
      end

      it 'append email to conversation with references id' do
        inbox = Inbox.last
        message = create(
          :message,
          content: 'Incoming Message',
          message_type: 'incoming',
          inbox: inbox,
          source_id: 'test-reference-id',
          account: account,
          conversation: conversation
        )
        conversation = message.conversation

        expect(conversation.messages.size).to eq(1)

        class_instance.process(references_email.mail, inbox.channel)

        expect(conversation.messages.size).to eq(2)
        expect(conversation.messages.last.content).to eq('References Email')
        expect(references_email.mail.references).to include('test-reference-id')
      end

      it 'append email to conversation with reference id string' do
        inbox = Inbox.last
        message = create(
          :message,
          content: 'Incoming Message',
          message_type: 'incoming',
          inbox: inbox,
          source_id: 'test-reference-id-2',
          account: account,
          conversation: conversation
        )
        conversation = message.conversation

        expect(conversation.messages.size).to eq(1)

        references_email.mail.references = 'test-reference-id-2'
        class_instance.process(references_email.mail, inbox.channel)

        expect(conversation.messages.size).to eq(2)
        expect(conversation.messages.last.content).to eq('References Email')
        expect(references_email.mail.references).to include('test-reference-id-2')
      end
    end

    context 'when a reply for a conversation has multiple in_reply_to' do
      let(:multiple_in_reply_to_mail) { create_inbound_email_from_fixture('multiple_in_reply_to.eml').mail }

      it 'creates conversation taking the first in_reply_to email' do
        class_instance.process(multiple_in_reply_to_mail, channel)
        expect(conversation.additional_attributes['in_reply_to']).to eq(multiple_in_reply_to_mail.in_reply_to.first)
      end
    end

    context 'when a reply to a conversation started by an agent' do
      let(:agent_conversation) { create(:conversation, account: account, inbox: channel.inbox, assignee: agent) }
      let(:reply_mail_with_fallback_reference) do
        # Simulate an email reply with a reference that matches FALLBACK_PATTERN
        reference_id = "account/#{account.id}/conversation/#{agent_conversation.uuid}@chatwoot.com"
        create_inbound_email_from_mail(
          from: 'email@gmail.com',
          to: 'imap@gmail.com',
          subject: 'Re: Agent started conversation',
          references: [reference_id]
        )
      end

      it 'appends email to the existing conversation using FALLBACK_PATTERN' do
        expect(agent_conversation.messages.size).to eq(0)

        class_instance.process(reply_mail_with_fallback_reference.mail, channel)

        agent_conversation.reload
        expect(agent_conversation.messages.size).to eq(1)
        expect(agent_conversation.messages.last.content_attributes['email']['from']).to eq(reply_mail_with_fallback_reference.mail.from)
      end
    end

    context 'when references contain both message and fallback patterns' do
      let(:agent_conversation) { create(:conversation, account: account, inbox: channel.inbox, assignee: agent) }
      let(:reply_mail_with_multiple_references) do
        # Multiple references including both patterns
        fallback_reference = "account/#{account.id}/conversation/#{agent_conversation.uuid}@chatwoot.com"
        other_reference = 'some-other-message-id@example.com'
        create_inbound_email_from_mail(
          from: 'email@gmail.com',
          to: 'imap@gmail.com',
          subject: 'Re: Multiple references',
          references: [other_reference, fallback_reference]
        )
      end

      it 'finds conversation using fallback pattern when message lookup fails' do
        expect(agent_conversation.messages.size).to eq(0)

        class_instance.process(reply_mail_with_multiple_references.mail, channel)

        agent_conversation.reload
        expect(agent_conversation.messages.size).to eq(1)
        expect(agent_conversation.messages.last.content_attributes['email']['from']).to eq(reply_mail_with_multiple_references.mail.from)
      end
    end
  end
end
