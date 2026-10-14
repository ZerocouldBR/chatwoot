# Business hours and holidays (Zendesk schedules); admins manage them, everyone can read them.
class Api::V1::Accounts::BusinessSchedulesController < Api::V1::Accounts::BaseController
  before_action :fetch_schedule, only: [:show, :update, :destroy]
  before_action :check_authorization

  def index
    render json: { payload: BusinessSchedule.where(account: Current.account).order(:id) }
  end

  def show
    render json: @schedule
  end

  def create
    render json: BusinessSchedule.create!(schedule_params.merge(account: Current.account))
  end

  def update
    @schedule.update!(schedule_params)
    render json: @schedule
  end

  def destroy
    @schedule.destroy!
    head :ok
  end

  private

  def fetch_schedule
    @schedule = BusinessSchedule.find_by!(account: Current.account, id: params[:id])
  end

  def schedule_params
    params.require(:business_schedule).permit(
      :name, :time_zone, :is_default, intervals: %i[day start end], holidays: %i[name start_date end_date]
    )
  end
end
