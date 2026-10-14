# POST /sc/v2/apps/:app_id/conversations/:conversation_id/activity  {type: typing:start|typing:stop|conversation:read}
# typing:* liga/desliga o "digitando" do usuário de integração na conversa; conversation:read é aceito sem efeito.
class ZendeskCompat::Sunshine::ActivitiesController < ZendeskCompat::Sunshine::BaseController
  TYPING = { 'typing:start' => 'on', 'typing:stop' => 'off' }.freeze

  def create
    conversation = find_conversation!
    type = body_params['type'].to_s
    raise ZendeskCompat::Error, "Atividade inválida: #{type}" unless TYPING.key?(type) || type == 'conversation:read'

    if TYPING.key?(type)
      Conversations::TypingStatusManager.new(conversation, context.user, { typing_status: TYPING[type], is_private: false }).toggle_typing_status
    end
    render json: {}
  end
end
