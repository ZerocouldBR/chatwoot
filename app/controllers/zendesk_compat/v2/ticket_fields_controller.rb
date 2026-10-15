# GET /api/v2/ticket_fields(.json) e /ticket_fields/:id: campos de ticket do Zendesk (config) com as opções.
# É também o teste de credencial do n8n (GET /api/v2/ticket_fields.json).
# rubocop:disable Metrics/AbcSize
class ZendeskCompat::V2::TicketFieldsController < ZendeskCompat::BaseController
  def index
    fields = ZendeskCompat::Config.ticket_fields.map { |field| field_json(field) }
    render json: { ticket_fields: fields, next_page: nil, previous_page: nil, count: fields.size }
  end

  def show
    field = ZendeskCompat::Config.ticket_field(params[:id]) || raise(ZendeskCompat::Error::NotFound)
    render json: { ticket_field: field_json(field) }
  end

  private

  def field_json(field)
    {
      id: field['id'], url: context.api_url("ticket_fields/#{field['id']}.json"), type: field['zendesk_type'], title: field['title'],
      raw_title: field['title'], description: field['description'].to_s, raw_description: field['description'].to_s,
      position: field['position'], active: field['active'], required: field['required'], collapsed_for_agents: false,
      regexp_for_validation: nil, title_in_portal: field['title'], raw_title_in_portal: field['title'],
      visible_in_portal: field['visible_in_portal'], editable_in_portal: false, required_in_portal: field['required_in_portal'],
      tag: field['tag'], removable: !field['system'], key: nil, agent_description: nil, sub_type_id: 0,
      custom_field_options: options(field), system_field_options: field['system'] ? options(field) : nil,
      servicedesk_attribute_key: field['system'] ? field['key'] : context.fields.attribute_key(field)
    }.compact
  end

  def options(field)
    Array(field['options']).each_with_index.map do |(tag, name), index|
      { id: (field['id'] * 1000) + index + 1, name: name, raw_name: name, value: tag, default: false }
    end
  end
end
# rubocop:enable Metrics/AbcSize
