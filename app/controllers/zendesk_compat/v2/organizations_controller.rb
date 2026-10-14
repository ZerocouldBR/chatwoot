# /api/v2/organizations: show e show_many (empresas). id = zd_org_id ou ORG_BASE + companies.id.
# rubocop:disable Metrics/AbcSize
class ZendeskCompat::V2::OrganizationsController < ZendeskCompat::BaseController
  def show
    company = context.directory.company(params[:id]) || raise(ZendeskCompat::Error::NotFound)
    render json: { organization: organization_json(company) }
  end

  def show_many
    companies = params[:ids].to_s.split(',').first(100).filter_map { |id| context.directory.company(id) }
    render json: { organizations: companies.map { |company| organization_json(company) }, next_page: nil, previous_page: nil, count: companies.size }
  end

  private

  def organization_json(company)
    id = ZendeskCompat::Ids.organization_id(company)
    zendesk = company.additional_attributes&.dig('zendesk') || {}
    {
      id: id, url: context.api_url("organizations/#{id}.json"), name: company.name, details: company.description.to_s,
      notes: zendesk['notes'].to_s, domain_names: [company.domain, *Array(zendesk['domain_names'])].compact_blank.uniq,
      group_id: ZendeskCompat::Ids.integer(zendesk['group_id']), shared_tickets: false, shared_comments: false,
      external_id: zendesk['external_id'], tags: Array(zendesk['tags']), organization_fields: organization_fields(company),
      created_at: context.time(company.created_at), updated_at: context.time(company.updated_at)
    }
  end

  def organization_fields(company)
    attributes = company.custom_attributes || {}
    ZendeskCompat::Config.data.fetch('org_fields', []).to_h do |field|
      value = field['attr'] && attributes[field['attr']]
      value = ZendeskCompat::Config.option_tag(field, value) if field['type'] == 'list' && value.present?
      [field['key'], field['type'] == 'checkbox' ? value.present? : value]
    end
  end
end
# rubocop:enable Metrics/AbcSize
