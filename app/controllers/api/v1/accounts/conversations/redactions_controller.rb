# Permanently redacts text and/or attachments of a comment: POST /conversations/:id/messages/:message_id/redaction
class Api::V1::Accounts::Conversations::RedactionsController < Api::V1::Accounts::Conversations::BaseController
  def create
    authorize @conversation, :destroy?
    message = @conversation.messages.find(params[:message_id])
    text = params[:text].to_s
    return render_could_not_create_error(I18n.t('errors.tickets.redaction.text_not_found')) if text.present? && message.content.to_s.exclude?(text)

    Tickets::RedactionService.new(message: message, user: Current.user, text: text, attachment_ids: params[:attachment_ids]).perform
    head :ok
  end
end
