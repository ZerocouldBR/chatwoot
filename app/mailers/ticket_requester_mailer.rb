# E-mail sent to the requester (and CCs) by a trigger or automation, through the ticket's channel and in its thread.
class TicketRequesterMailer < ConversationReplyMailer
  def ticket_notification(conversation, to:, cc:, subject:, body:)
    init_conversation_attributes(conversation)
    return unless smtp_config_set_or_development? || email_smtp_enabled? || (email_imap_enabled? && email_oauth_enabled?)

    @body = body
    @options = { to: to, cc: cc.presence, from: email_from, reply_to: email_reply_to, subject: subject,
                 in_reply_to: in_reply_to_email, references: references_header }
    oauth_smtp_settings
    set_delivery_method
    mail(@options)
  end
end
