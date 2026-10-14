# /sc/v2/apps/:app_id/conversations/:conversation_id/messages
#   GET  mensagens públicas da conversa (author.type user = cliente, business = agente/bot)
#   POST envia uma mensagem como o usuário de integração: content {type:text, text} ou {type:image|file, mediaUrl}
#        (mediaUrl de POST /sc/v2/.../attachments ou de um anexo do ServiceDesk; URL externa não é baixada)
class ZendeskCompat::Sunshine::MessagesController < ZendeskCompat::Sunshine::BaseController
  def index
    conversation = find_conversation!
    messages = ZendeskCompat::CommentPresenter.comment_scope(conversation).where(private: false).order(:created_at, :id).last(100)
    render json: { messages: messages.map { |message| serializer.message_json(message) }, meta: { hasMore: false }, links: {} }
  end

  def create
    conversation = find_conversation!
    message = ZendeskCompat::SunshineMessageCreator.new(context, conversation, body_params).perform
    render json: { messages: [serializer.message_json(message)] }, status: :created
  end

  private

  def serializer
    @serializer ||= ZendeskCompat::SunshineSerializer.new(context)
  end
end
