# "Mark as spam": the requester is blocked (their next e-mails are suspended) and the ticket goes to the trash.
class Api::V1::Accounts::Conversations::SpamsController < Api::V1::Accounts::Conversations::BaseController
  def create
    authorize @conversation, :destroy?
    @conversation.contact.update!(blocked: true)
    Conversations::DeleteService.new(conversation: @conversation, user: Current.user, ip: request.ip).perform
    head :ok
  end
end
