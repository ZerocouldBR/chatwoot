# SLA report: the SLA applied to each ticket in the period, its breaches and the hit rate.
class Api::V1::Accounts::AppliedSlasController < Api::V1::Accounts::BaseController
  RESULTS_PER_PAGE = 25

  before_action -> { authorize :report, :view? }

  def index
    page = params.fetch(:page, 1).to_i
    records = applied_slas.includes(:sla_policy, :sla_events, conversation: [:contact, :assignee]).order(created_at: :desc)
    render json: { payload: records.page(page).per(RESULTS_PER_PAGE).map { |applied| row(applied) },
                   meta: { count: records.count, current_page: page } }
  end

  def metrics
    total = applied_slas.count
    missed = applied_slas.missed.count
    hit_rate = total.zero? ? 0 : ((total - missed) * 100.0 / total).round(1)
    render json: { total_applied_slas: total, number_of_sla_misses: missed, hit_rate: "#{hit_rate}%" }
  end

  def download
    csv = CSV.generate do |rows|
      rows << %w[ticket policy status assignee breached_metrics]
      applied_slas.includes(:sla_policy, :sla_events, conversation: :assignee).find_each do |applied|
        rows << [applied.conversation.display_id, applied.sla_policy.name, applied.sla_status, applied.conversation.assignee&.name,
                 applied.sla_events.select(&:breach?).map { |event| event.meta['metric'] }.uniq.join(' ')]
      end
    end
    send_data csv, filename: 'sla_report.csv'
  end

  private

  def applied_slas
    scope = AppliedSla.where(account: Current.account, conversation_id: conversations.select(:id))
    scope = scope.where(created_at: period) if params[:since].present? && params[:until].present?
    scope = scope.where(sla_policy_id: params[:sla_policy_id]) if params[:sla_policy_id].present?
    scope
  end

  def conversations
    scope = Current.account.conversations
    filters = { assignee_id: params[:assigned_agent_id], inbox_id: params[:inbox_id], team_id: params[:team_id] }.compact_blank
    scope = scope.where(filters) if filters.any?
    scope = scope.tagged_with(params[:label_list]) if params[:label_list].present?
    scope
  end

  def period
    Time.zone.at(params[:since].to_i)..Time.zone.at(params[:until].to_i)
  end

  def row(applied)
    conversation = applied.conversation
    {
      applied_sla: { id: applied.id, sla_name: applied.sla_policy.name, sla_status: applied.sla_status },
      conversation: {
        id: conversation.display_id,
        contact: { name: conversation.contact.name },
        assignee: conversation.assignee&.then { |user| { id: user.id, name: user.name, thumbnail: user.avatar_url } },
        labels: conversation.cached_label_list
      },
      sla_events: applied.sla_events.select(&:breach?).map do |event|
        { id: event.id, metric: event.meta['metric'], created_at: event.created_at.to_i }
      end
    }
  end
end
