# An e-mail held instead of becoming a ticket (Zendesk "Suspended tickets"), with the original message so an agent
# can recover it (it is then processed as usual) or delete it. Held e-mails are purged after RETENTION.
class SuspendedTicket < ApplicationRecord
  REASONS = %w[blocked_sender automated_response].freeze
  RETENTION = 14.days

  belongs_to :account
  belongs_to :inbox
  has_one_attached :raw_email

  validates :reason, inclusion: { in: REASONS }
  validates :from_email, presence: true

  scope :held, -> { where(recovered_at: nil) }

  # Holds an incoming e-mail from a blocked requester or an automatic reply; returns whether it was held.
  def self.hold_if_needed(inbox, processed_mail, raw)
    reason = reason_for(inbox, processed_mail)
    return false if reason.nil?

    held = create!(account: inbox.account, inbox: inbox, reason: reason, from_email: processed_mail.original_sender,
                   from_name: processed_mail.sender_name, subject: processed_mail.subject, message_id: message_id(processed_mail))
    held.raw_email.attach(io: StringIO.new(raw), filename: "#{held.id}.eml", content_type: 'message/rfc822')
    true
  end

  def self.reason_for(inbox, processed_mail)
    return if where(inbox: inbox, message_id: message_id(processed_mail)).where.not(recovered_at: nil).exists?
    return 'blocked_sender' if inbox.account.contacts.from_email(processed_mail.original_sender.to_s)&.blocked?

    # Bounces still reach the ticket so agents see the delivery failure.
    'automated_response' if processed_mail.auto_reply? && !processed_mail.bounced?
  end

  # Postgres strings cannot hold null bytes, which malformed e-mails may carry.
  def self.message_id(processed_mail)
    processed_mail.message_id.to_s.delete("\u0000")
  end
  private_class_method :reason_for, :message_id

  # Runs the held e-mail through the inbox again; the recovered mark lets it past the suspension check.
  def recover!
    update!(recovered_at: Time.current)
    raw = raw_email.download
    if inbox.channel.try(:imap_enabled)
      Imap::ImapMailbox.new.process(Mail.new(raw), inbox.channel)
    else
      ActionMailbox::InboundEmail.create_and_extract_message_id!(raw)
    end
  end
end
