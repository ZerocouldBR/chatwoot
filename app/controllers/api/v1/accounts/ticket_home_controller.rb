# Agent home page: the agent's ticket lists and the numbers beside them.
class Api::V1::Accounts::TicketHomeController < Api::V1::Accounts::BaseController
  before_action :validate_view, only: :index

  def index
    query = Tickets::HomeQuery.new(account: Current.account, user: Current.user)
    @conversations = query.tickets(params[:view], page: params[:page] || 1)
    @counts = query.counts
  end

  def stats
    render json: Tickets::HomeStats.new(account: Current.account, user: Current.user)
  end

  private

  def validate_view
    return if Tickets::HomeQuery::VIEWS.include?(params[:view])

    render_could_not_create_error(I18n.t('errors.ticket_home.invalid_view'))
  end
end
