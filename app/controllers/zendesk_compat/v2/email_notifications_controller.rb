# GET /api/v2/email_notifications?filter[ticket_id]=N: entregas de e-mail dos comentários públicos do ticket.
# Destinatários = solicitante (to) + CCs da mensagem; delivery_status pela situação da mensagem no ServiceDesk
# (enviada/entregue/lida ou falha com o erro do servidor). O ServiceDesk não recebe bounce por destinatário:
# numa falha, todos os destinatários da mensagem levam o mesmo status (erro de endereço -> invalid_recipient).
class ZendeskCompat::V2::EmailNotificationsController < ZendeskCompat::BaseController
  HARD_ERROR = /invalid|does not exist|unknown user|no such user|rejected|not found|550|553|mailbox unavailable/i

  def index
    ticket_id = params.dig(:filter, :ticket_id)
    raise ZendeskCompat::Error, 'Use filter[ticket_id]' if ticket_id.blank?

    conversation = find_ticket!(ticket_id)
    scope = conversation.messages.where(message_type: :outgoing, private: false).order(:created_at, :id)
    messages, links = paginate(conversation.inbox.email? ? scope : scope.none)
    render json: { email_notifications: messages.map { |message| notification_json(conversation, message) } }
      .merge(links).merge(meta: { has_more: links[:next_page].present? })
  end

  private

  def notification_json(conversation, message)
    {
      notification_id: message.id, comment_id: message.id, ticket_id: conversation.display_id, email_id: message.source_id,
      message_id: message.source_id, created_at: context.time(message.created_at), updated_at: context.time(message.updated_at),
      recipients: recipients(conversation, message).map { |email| recipient_json(email, message) }
    }
  end

  def recipients(conversation, message)
    attrs = message.content_attributes || {}
    to = Array(attrs['to_emails']).presence || [conversation.contact&.email]
    (to + Array(attrs['cc_emails'])).compact_blank.map(&:downcase).uniq
  end

  def recipient_json(email, message)
    actor = context.directory.actor_by_email(email)
    { user_id: actor && ZendeskCompat::Ids.user_id(actor), email_address: email, delivery_status: delivery_status(message),
      delivered_at: message.failed? ? nil : context.time(message.updated_at) }
  end

  def delivery_status(message)
    return { id: 1, name: 'delivered', code: '250', message: '' } unless message.failed?

    error = message.external_error.to_s
    return { id: 37, name: 'invalid_recipient', code: '550', message: error } if error.match?(HARD_ERROR)

    { id: 0, name: 'delivery_failed', code: '', message: error }
  end
end
