# Suspended tickets: e-mails held instead of becoming tickets. Recovering processes the e-mail as usual.
class Api::V1::Accounts::SuspendedTicketsController < Api::V1::Accounts::BaseController
  RESULTS_PER_PAGE = 25

  before_action :check_authorization
  before_action :fetch_suspended_ticket, only: [:recover, :destroy]

  def index
    page = params.fetch(:page, 1).to_i
    held = SuspendedTicket.held.where(account: Current.account).includes(:inbox).order(created_at: :desc)
    render json: { payload: held.page(page).per(RESULTS_PER_PAGE).map { |ticket| row(ticket) },
                   meta: { count: held.count, current_page: page } }
  end

  def recover
    @suspended_ticket.recover!
    head :ok
  end

  def destroy
    @suspended_ticket.destroy!
    head :ok
  end

  private

  def fetch_suspended_ticket
    @suspended_ticket = SuspendedTicket.held.find_by!(account: Current.account, id: params[:id])
  end

  def row(ticket)
    timestamps = { created_at: ticket.created_at.to_i, purge_at: (ticket.created_at + SuspendedTicket::RETENTION).to_i }
    ticket.slice(:id, :from_email, :from_name, :subject, :reason).merge(inbox: ticket.inbox.name, **timestamps)
  end
end
