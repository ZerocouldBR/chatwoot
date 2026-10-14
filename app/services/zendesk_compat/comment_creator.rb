# Objeto "comment" do Zendesk -> mensagem do ServiceDesk.
#   public: true (padrão) -> mensagem enviada ao cliente pelo canal da conversa; false -> nota interna
#   author_id: agente ou bot (padrão: usuário autenticado); contato -> mensagem do cliente (registrada, não enviada)
#   body (texto) ou html_body (convertido para markdown); uploads: tokens de POST /api/v2/uploads
#   e-mail público: os CCs do ticket (zd_cc) vão em cópia, como no Zendesk
class ZendeskCompat::CommentCreator
  def initialize(context, conversation, comment)
    @context = context
    @conversation = conversation
    @comment = comment.is_a?(String) ? { body: comment } : (comment || {}).to_h.with_indifferent_access
  end

  def perform
    validate!
    author = resolve_author
    return create_contact_message(author) if author.is_a?(Contact)

    Messages::MessageBuilder.new(author, @conversation, builder_params(author)).perform
  end

  private

  def validate!
    return if content.present? || blobs.any?

    raise ZendeskCompat::Error::RecordInvalid, { comment: [{ description: 'Comment: body não pode ficar em branco', error: 'BlankValue' }] }
  end

  def public?
    @comment.key?(:public) ? ActiveModel::Type::Boolean.new.cast(@comment[:public]) != false : true
  end

  def content
    @content ||= if @comment[:html_body].present?
                   ReverseMarkdown.convert(@comment[:html_body].to_s, unknown_tags: :bypass, github_flavored: true).strip
                 else
                   @comment[:body].to_s.presence || @comment[:value].to_s
                 end
  end

  def blobs
    @blobs ||= Array(@comment[:uploads]).map do |token|
      ZendeskCompat::Uploads.find(token) || raise(ZendeskCompat::Error::RecordInvalid,
                                                  { uploads: [{ description: "Upload token inválido ou expirado: #{token}",
                                                                error: 'InvalidValue' }] })
    end
  end

  def resolve_author
    return @context.user if @comment[:author_id].blank?

    @context.directory.actor(@comment[:author_id]) ||
      raise(ZendeskCompat::Error::RecordInvalid,
            { author_id: [{ description: "Author: #{@comment[:author_id]} não existe", error: 'InvalidValue' }] })
  end

  def builder_params(author)
    params = { content: content, private: !public?, message_type: 'outgoing', attachments: blobs.map(&:signed_id) }
    if author.is_a?(AgentBot)
      params[:sender_type] = 'AgentBot'
      params[:sender_id] = author.id
    end
    cc_emails = ZendeskCompat::CcList.parse((@conversation.custom_attributes || {})[ZendeskCompat::CcList::ATTRIBUTE])
    params[:cc_emails] = cc_emails.join(',') if public? && @conversation.inbox.email? && cc_emails.any?
    params.with_indifferent_access
  end

  def create_contact_message(contact)
    message = @conversation.messages.build(
      account_id: @conversation.account_id, inbox_id: @conversation.inbox_id, message_type: :incoming, sender: contact,
      content: content, private: !public?, additional_attributes: { 'zendesk_compat' => { 'author_type' => 'end-user' } }
    )
    blobs.each { |blob| message.attachments.build(account_id: @conversation.account_id, file: blob.signed_id, file_type: file_type(blob)) }
    message.save!
    message
  end

  def file_type(blob)
    case blob.content_type.to_s
    when %r{\Aimage/} then :image
    when %r{\Aaudio/} then :audio
    when %r{\Avideo/} then :video
    else :file
    end
  end
end
