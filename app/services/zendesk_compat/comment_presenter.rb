# Mensagem do ServiceDesk -> comentário do Zendesk. Nota privada = comentário interno (public: false).
# Mensagens de atividade (atribuição, status...) não são comentários: viram eventos Change nos audits.
class ZendeskCompat::CommentPresenter
  COMMENT_TYPES = %w[incoming outgoing template].freeze

  def self.comment_scope(conversation)
    conversation.messages.where(message_type: COMMENT_TYPES).includes(:sender, attachments: { file_attachment: :blob })
  end

  def initialize(context)
    @context = context
  end

  def present(message)
    {
      id: message.id, type: 'Comment', author_id: author_id(message), body: plain_body(message), html_body: html_body(message),
      plain_body: plain_body(message), public: !message.private, attachments: attachments(message), audit_id: message.id,
      via: via(message), created_at: @context.time(message.created_at), metadata: { system: {}, custom: {} }
    }
  end

  def author_id(message)
    return ZendeskCompat::Ids.user_id(message.sender) if message.sender

    origin = message.additional_attributes&.dig('zendesk', 'author_id')
    origin ||= ZendeskCompat::Ids.contact_id(message.conversation.contact) if message.incoming?
    ZendeskCompat::Ids.integer(origin) || -1
  end

  def attachments(message)
    message.attachments.select { |attachment| attachment.file.attached? }.map { |attachment| attachment_json(attachment) }
  end

  def attachment_json(attachment)
    blob_json(attachment.file.blob, id: attachment.id)
  end

  def blob_json(blob, id:)
    url = @context.blob_url(blob)
    {
      id: id, url: @context.api_url("attachments/#{id}.json"), file_name: blob.filename.to_s,
      content_url: url, mapped_content_url: url, content_type: blob.content_type, size: blob.byte_size,
      width: blob.metadata['width'], height: blob.metadata['height'], inline: false, deleted: false,
      malware_access_override: false, malware_scan_result: 'not_scanned', thumbnails: []
    }
  end

  private

  def html_body(message)
    email_html = message.content_attributes&.dig('email', 'html_content', 'full')
    return email_html if email_html.present?

    ChatwootMarkdownRenderer.new(message.content.to_s).render_message.to_s
  end

  def plain_body(message)
    text = message.content_attributes&.dig('email', 'text_content', 'full')
    return text if text.present? && message.content.blank?

    message.content.to_s
  end

  def via(message)
    channel = message.content_type == 'incoming_email' || message.conversation.inbox&.email? ? 'email' : 'api'
    channel = 'web' if message.outgoing? && message.sender.is_a?(User) && channel != 'email'
    { channel: channel, source: { from: {}, to: {}, rel: nil } }
  end
end
