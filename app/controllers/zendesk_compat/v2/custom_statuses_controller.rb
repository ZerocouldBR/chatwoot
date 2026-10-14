# GET /api/v2/custom_statuses(.json) e /custom_statuses/:id: status personalizados (config/servicedesk/ticket_statuses.yml).
class ZendeskCompat::V2::CustomStatusesController < ZendeskCompat::BaseController
  def index
    statuses = ZendeskCompat::StatusTranslator.statuses
    statuses = statuses.select { |status| status['active'] } if params[:active].to_s == 'true'
    render json: { custom_statuses: statuses.map { |status| status_json(status) } }
  end

  def show
    status = ZendeskCompat::StatusTranslator.status_for_origin_id(params[:id]) || raise(ZendeskCompat::Error::NotFound)
    render json: { custom_status: status_json(status) }
  end

  private

  def status_json(status)
    extra = ZendeskCompat::Config.custom_statuses[status['origin_id'].to_s] || {}
    {
      id: status['origin_id'], url: context.api_url("custom_statuses/#{status['origin_id']}.json"), status_category: status['category'],
      agent_label: status['label'], raw_agent_label: status['label'], end_user_label: extra['end_user_label'] || status['label'],
      raw_end_user_label: extra['end_user_label'] || status['label'], description: '', raw_description: '',
      end_user_description: '', raw_end_user_description: '', active: status['active'], default: extra['default'] || false,
      created_at: nil, updated_at: nil
    }
  end
end
