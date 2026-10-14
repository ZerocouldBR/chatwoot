# Mensagem do ServiceDesk -> mensagem da API Sunshine Conversations (v2).
# rubocop:disable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
class ZendeskCompat::SunshineSerializer
  def initialize(context)
    @context = context
  end

  def message_json(message)
    {
      id: "sd-msg-#{message.id}", received: @context.time(message.created_at), author: author(message), content: content(message),
      source: { type: source_type(message) }, metadata: { 'sd:message_id' => message.id }
    }
  end

  private

  def author(message)
    if message.incoming?
      contact = message.conversation.contact
      return { type: 'user', userId: ZendeskCompat::ConversationLogBuilder.sunco_user_id(contact), displayName: contact&.name }
    end

    compat = message.additional_attributes&.dig('zendesk_compat') || {}
    { type: 'business', displayName: compat['display_name'] || message.sender&.name || 'Bot', avatarUrl: compat['avatar_url'],
      userId: message.sender ? ZendeskCompat::Ids.user_id(message.sender).to_s : nil }.compact
  end

  def content(message)
    attachment = message.attachments.find { |item| item.file.attached? }
    return { type: 'text', text: message.content.to_s } unless attachment

    blob = attachment.file.blob
    type = blob.content_type.to_s.start_with?('image/') ? 'image' : 'file'
    { type: type, text: message.content.presence, mediaUrl: @context.blob_url(blob), mediaType: blob.content_type,
      altText: blob.filename.to_s }.compact
  end

  def source_type(message)
    message.incoming? ? ZendeskCompat::TicketPresenter.new(@context).channel(message.conversation) : 'api:conversations'
  end
end
# rubocop:enable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
