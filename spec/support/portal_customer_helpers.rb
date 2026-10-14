# ServiceDesk B2B: apoio às specs do portal do cliente (login do contato e empresas).
module PortalCustomerHelpers
  def sd_create_company(account, name:, custom_attributes: {})
    Company.create!(account: account, name: name, custom_attributes: custom_attributes).id
  end

  def sd_magic_link_token(portal, contact, locale: 'pt_BR', return_to: nil)
    Redis::Alfred.delete("#{PortalCustomers::MagicLinkService::KEY_PREFIX}:COOLDOWN:#{portal.id}:#{contact.id}")
    result = PortalCustomers::MagicLinkService.new(portal: portal).request!(email: contact.email, locale: locale, return_to: return_to)
    return if result.url.blank?

    Rack::Utils.parse_query(URI.parse(result.url).query)['token']
  end

  def sd_sign_in(portal, contact, locale: 'pt_BR')
    token = sd_magic_link_token(portal, contact, locale: locale)
    post "/hc/#{portal.slug}/#{locale}/login/verify", params: { token: token }
    expect(response).to have_http_status(:redirect)
  end
end

RSpec.configure do |config|
  config.include PortalCustomerHelpers, type: :request
end
