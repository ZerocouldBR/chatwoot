# Zendesk-style SLA policies: ordered, with conditions and per-priority targets.
class Api::V1::Accounts::SlaPoliciesController < Api::V1::Accounts::BaseController
  before_action :fetch_policy, only: [:show, :update, :destroy]
  before_action :check_authorization

  def index
    render json: { payload: SlaPolicy.where(account: Current.account).ordered }
  end

  def show
    render json: @policy
  end

  def create
    position = SlaPolicy.where(account: Current.account).maximum(:position).to_i + 1
    render json: SlaPolicy.create!(policy_params.merge(account: Current.account, position: position))
  end

  def update
    @policy.update!(policy_params)
    render json: @policy
  end

  def destroy
    @policy.destroy!
    head :ok
  end

  # Matching follows this order: the first policy whose conditions match a ticket applies.
  def reorder
    policies = SlaPolicy.where(account: Current.account).index_by(&:id)
    Array(params[:ids]).map(&:to_i).each_with_index { |id, index| policies[id]&.update!(position: index + 1) }
    render json: { payload: SlaPolicy.where(account: Current.account).ordered }
  end

  private

  def fetch_policy
    @policy = SlaPolicy.find_by!(account: Current.account, id: params[:id])
  end

  def policy_params
    params.require(:sla_policy).permit(
      :name, :description,
      filter: { all: [:field, :operator, :value], any: [:field, :operator, :value] },
      targets: %i[metric priority minutes business_hours]
    )
  end
end
