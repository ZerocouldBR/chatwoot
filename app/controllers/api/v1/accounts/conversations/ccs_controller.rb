# The ticket's CC list: people copied on every public reply.
class Api::V1::Accounts::Conversations::CcsController < Api::V1::Accounts::Conversations::BaseController
  before_action :validate_email, only: [:create, :destroy]

  def show
    render json: { payload: cc_list.emails }
  end

  def create
    author, via = TicketAuditable.current_actor
    render json: { payload: cc_list.add(params[:email], author: author, via: via) }
  end

  def destroy
    author, via = TicketAuditable.current_actor
    render json: { payload: cc_list.remove(params[:email], author: author, via: via) }
  end

  private

  def cc_list
    @cc_list ||= Tickets::CcList.new(@conversation)
  end

  def validate_email
    return if Devise.email_regexp.match?(params[:email].to_s.strip)

    render_could_not_create_error(I18n.t('errors.conversations.invalid_cc'))
  end
end
