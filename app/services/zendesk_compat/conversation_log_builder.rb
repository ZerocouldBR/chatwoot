# GET /api/v2/tickets/:id/conversation_log (log da mensageria do Zendesk, usado pelos workflows de chat/WhatsApp).
# Mensagem pública em canal de mensageria -> evento "Messaging::ConversationMessage" com author.type
#   'end-user' (contato), 'business' (bot, IA ou envio pela API Sunshine de compatibilidade) ou 'agent' (agente humano);
# nota interna e mensagens de e-mail -> evento "Comment" com metadata.public.
# rubocop:disable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
class ZendeskCompat::ConversationLogBuilder
  BOT_AUTHOR_TYPES = %w[bot system business].freeze

  def initialize(context, conversation)
    @context = context
    @conversation = conversation
    @comments = ZendeskCompat::CommentPresenter.new(context)
    @messaging = ZendeskCompat::TicketPresenter::MESSAGING_CHANNELS.include?(ZendeskCompat::TicketPresenter.new(context).channel(conversation))
  end

  def events
    ZendeskCompat::CommentPresenter.comment_scope(@conversation).order(:created_at, :id).map do |message|
      @messaging && !message.private ? messaging_event(message) : comment_event(message)
    end
  end

  def self.sunco_user_id(contact)
    "sd-contact-#{contact.id}"
  end

  private

  def messaging_event(message)
    {
      id: "sd-msg-#{message.id}", type: 'Messaging::ConversationMessage', author: author(message), content: content(message),
      created_at: @context.time(message.created_at), received_at: @context.time(message.created_at),
      source: { type: source_type }, metadata: { message_id: message.id }
    }
  end

  def comment_event(message)
    comment = @comments.present(message)
    {
      id: "sd-comment-#{message.id}", type: 'Comment', author: author(message),
      content: { type: 'text', body: comment[:html_body], text: comment[:plain_body] },
      created_at: comment[:created_at], received_at: comment[:created_at],
      metadata: { public: comment[:public], is_public: comment[:public], comment_id: message.id }
    }
  end

  def author(message)
    author_id = @comments.author_id(message)
    base = { display_name: display_name(message), 'zen:support:user_id': author_id }
    case author_type(message)
    when 'end-user' then base.merge(type: 'end-user', 'zen:sunco:user_id': self.class.sunco_user_id(@conversation.contact))
    when 'business' then base.merge(type: 'business', subtypes: ['AI'])
    else base.merge(type: 'agent', role: agent_role(message))
    end
  end

  def author_type(message)
    compat = message.additional_attributes&.dig('zendesk_compat', 'author_type')
    return 'business' if BOT_AUTHOR_TYPES.include?(compat)
    return 'end-user' if message.incoming?

    imported = message.additional_attributes&.dig('zendesk', 'author_type')
    return 'business' if BOT_AUTHOR_TYPES.include?(imported) || message.sender.is_a?(AgentBot)

    imported == 'agent' || message.sender.is_a?(User) ? 'agent' : 'business'
  end

  def agent_role(message)
    account_user = message.sender.is_a?(User) ? @context.account_user(message.sender) : nil
    account_user&.administrator? ? 'admin' : 'agent'
  end

  def display_name(message)
    message.additional_attributes&.dig('zendesk_compat', 'display_name') || message.sender&.name ||
      message.additional_attributes&.dig('author_name') || 'Bot'
  end

  def content(message)
    attachment = message.attachments.find { |item| item.file.attached? }
    return { type: 'text', text: message.content.to_s } unless attachment

    blob = attachment.file.blob
    type = blob.content_type.to_s.start_with?('image/') ? 'image' : 'file'
    { type: type, text: message.content.to_s, media_url: @context.blob_url(blob), media_type: blob.content_type }
  end

  def source_type
    ZendeskCompat::TicketPresenter.new(@context).channel(@conversation)
  end
end
# rubocop:enable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
