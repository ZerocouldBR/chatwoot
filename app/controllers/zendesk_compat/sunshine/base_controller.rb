# Base da compatibilidade com a API de mensageria do Zendesk (Sunshine Conversations, /sc/v2/apps/:app_id/...),
# usada pelos workflows de WhatsApp/chat. conversation id = conversations.uuid (ou o nº do ticket);
# userId = "sd-contact-<contacts.id>" (o mesmo de author["zen:sunco:user_id"] no conversation_log). app_id é ignorado.
class ZendeskCompat::Sunshine::BaseController < ZendeskCompat::BaseController
  rescue_from ZendeskCompat::Error, with: :render_sunshine_error

  private

  def find_conversation!(id = params[:conversation_id])
    scope = current_account.conversations
    conversation = scope.find_by(uuid: id.to_s) if id.to_s.match?(/\A\h{8}-\h{4}-\h{4}-\h{4}-\h{12}\z/)
    conversation ||= scope.find_by(display_id: ZendeskCompat::Ids.integer(id)) if ZendeskCompat::Ids.integer(id)
    conversation || raise(ZendeskCompat::Error::NotFound, 'Conversation not found')
  end

  def render_sunshine_error(error)
    code = error.is_a?(ZendeskCompat::Error::NotFound) ? 'conversation_not_found' : 'bad_request'
    render json: { errors: [{ code: code, title: error.message }] }, status: error.status
  end

  def render_not_found(_error = nil)
    render json: { errors: [{ code: 'not_found', title: 'Not found' }] }, status: :not_found
  end
end
