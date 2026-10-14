# Zendesk triggers and automations (`kind`), each kept in its own order.
class Api::V1::Accounts::TicketRulesController < Api::V1::Accounts::BaseController
  CONDITION_KEYS = %i[field operator value business_hours].freeze

  before_action :check_authorization
  before_action :validate_kind, only: [:index, :create, :reorder]
  before_action :fetch_rule, only: [:show, :update, :destroy]

  def index
    render json: { payload: rules(params[:kind]) }
  end

  def show
    render json: @rule
  end

  def create
    position = rules(params[:kind]).maximum(:position).to_i + 1
    render json: TicketRule.create!(rule_params.merge(account: Current.account, kind: params[:kind], position: position))
  end

  def update
    @rule.update!(rule_params)
    render json: @rule
  end

  def destroy
    @rule.destroy!
    head :ok
  end

  def reorder
    by_id = rules(params[:kind]).index_by(&:id)
    Array(params[:ids]).map(&:to_i).each_with_index { |id, index| by_id[id]&.update!(position: index + 1) }
    render json: { payload: rules(params[:kind]) }
  end

  private

  def rules(kind)
    TicketRule.where(account: Current.account, kind: kind).ordered
  end

  def validate_kind
    render_could_not_create_error(I18n.t('errors.ticket_rules.invalid_kind')) unless TicketRule.kinds.key?(params[:kind])
  end

  def fetch_rule
    @rule = TicketRule.find_by!(account: Current.account, id: params[:id])
  end

  def rule_params
    params.require(:ticket_rule).permit(
      :title, :description, :active,
      conditions: { all: CONDITION_KEYS, any: CONDITION_KEYS },
      actions: [:field, :value, { value: %i[subject body team_id user_id] }]
    )
  end
end
