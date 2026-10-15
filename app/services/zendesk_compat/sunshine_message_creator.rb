# POST /sc/v2/.../messages: envia a mensagem pela conversa do ServiceDesk como o usuário de integração.
# author.type "business" (padrão) -> mensagem de saída; displayName/avatarUrl ficam na mensagem para o log.
# content.text -> texto; content.mediaUrl -> anexo, só de URL de arquivo do próprio ServiceDesk (sem baixar URL externa).
# rubocop:disable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
class ZendeskCompat::SunshineMessageCreator
  BLOB_PATH = %r{/rails/active_storage/blobs/(?:redirect/|proxy/)?([^/]+)/}

  def initialize(context, conversation, body)
    @context = context
    @conversation = conversation
    @body = (body || {}).to_h.with_indifferent_access
  end

  def perform
    author = @body[:author] || {}
    raise ZendeskCompat::Error, 'Somente author.type "business" é aceito' if author[:type].present? && author[:type] != 'business'

    content = @body[:content] || {}
    params = { content: content[:text].to_s.presence || content[:altText], message_type: 'outgoing', private: false,
               attachments: attachments(content) }
    raise ZendeskCompat::Error, 'content.text ou content.mediaUrl é obrigatório' if params[:content].blank? && params[:attachments].empty?

    message = Messages::MessageBuilder.new(@context.user, @conversation, params.with_indifferent_access).perform
    # rubocop:disable Rails/SkipsModelValidations
    message.update_columns(additional_attributes: (message.additional_attributes || {}).merge('zendesk_compat' => compat_attributes(author)))
    # rubocop:enable Rails/SkipsModelValidations
    message
  end

  private

  def compat_attributes(author)
    { 'author_type' => 'business', 'display_name' => author[:displayName], 'avatar_url' => author[:avatarUrl] }.compact
  end

  def attachments(content)
    url = content[:mediaUrl].to_s
    return [] if url.blank?

    signed_id = url[BLOB_PATH, 1]
    blob = signed_id && ActiveStorage::Blob.find_signed(signed_id)
    raise ZendeskCompat::Error, 'mediaUrl precisa ser um arquivo enviado ao ServiceDesk (POST /sc/v2/apps/:app/attachments)' if blob.nil?

    [blob.signed_id]
  end
end
# rubocop:enable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
