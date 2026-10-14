# The trash: deleted tickets can be restored or deleted for good until they are purged.
class Api::V1::Accounts::DeletedTicketsController < Api::V1::Accounts::BaseController
  RESULTS_PER_PAGE = 25

  before_action -> { authorize Conversation, :destroy? }
  before_action :fetch_ticket, only: [:restore, :destroy]

  def index
    page = params.fetch(:page, 1).to_i
    tickets = Current.account.conversations.trashed.includes(:contact).order(deleted_at: :desc)
    render json: { payload: tickets.page(page).per(RESULTS_PER_PAGE).map { |ticket| row(ticket) },
                   meta: { count: tickets.count, current_page: page } }
  end

  def restore
    @ticket.restore!
    head :ok
  end

  def destroy
    Tickets::PurgeTicketJob.perform_later(@ticket.id)
    head :ok
  end

  private

  def fetch_ticket
    @ticket = Current.account.conversations.trashed.find_by!(display_id: params[:id])
  end

  def row(ticket)
    { id: ticket.display_id, subject: ticket.subject, status: ticket.status, requester: ticket.contact.name,
      deleted_at: ticket.deleted_at.to_i, purge_at: (ticket.deleted_at + TicketTrashable::TRASH_RETENTION).to_i }
  end
end
