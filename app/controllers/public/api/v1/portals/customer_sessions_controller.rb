# ServiceDesk B2B: login do usuário final (contato) na Central de Ajuda.
#
# Fluxo principal (link mágico, sem senha):
#   GET  /hc/:slug/:locale/login              formulário de e-mail
#   POST /hc/:slug/:locale/login              envia o link (resposta igual exista ou não o e-mail)
#   GET  /hc/:slug/:locale/login/verify       página com o botão "Entrar" (não consome o token, para
#                                              os antivírus de e-mail que abrem links não queimarem o acesso)
#   POST /hc/:slug/:locale/login/verify       consome o token (uso único) e cria a sessão
# SSO do HUB (formato JWT do Zendesk): GET /hc/:slug/:locale/sso/jwt?jwt=...&return_to=...
# Sair: DELETE /hc/:slug/:locale/logout
class Public::Api::V1::Portals::CustomerSessionsController < Public::Api::V1::Portals::BaseController
  before_action :ensure_custom_domain_request
  before_action :portal
  before_action :set_portal_layout
  before_action :set_view_variant
  before_action :ensure_portal_feature_enabled
  before_action :ensure_customer_portal_enabled!
  before_action :verify_authenticity_token, only: [:create, :confirm, :destroy]
  layout 'portal'

  def new
    return redirect_to(after_login_path(params[:return_to])) if portal_contact_signed_in?
    return redirect_to(remote_login_url, allow_other_host: true) if remote_login_url.present? && params[:local] != '1'

    @return_to = safe_portal_return_to(params[:return_to])
  end

  def create
    @return_to = safe_portal_return_to(params[:return_to])
    magic_link_service.request!(email: params[:email], locale: @locale, return_to: @return_to, base_url: request.base_url)
    @email = params[:email].to_s.strip.first(254)
    @link_requested = true
    @email_dormant = !PortalCustomers::MagicLinkService.email_delivery_enabled?
    render :new
  end

  def verify
    @token = params[:token].to_s
    @token_valid = magic_link_service.valid_token?(@token)
    render :verify, status: (@token_valid ? :ok : :unprocessable_entity)
  end

  def confirm
    contact, return_to = magic_link_service.consume!(params[:token].to_s)
    if contact.blank?
      @token_valid = false
      return render(:verify, status: :unprocessable_entity)
    end

    reset_session
    sign_in_portal_contact(contact)
    redirect_to after_login_path(return_to)
  end

  def jwt
    contact = PortalCustomers::JwtLoginService.new(portal: @portal, token: params[:jwt].to_s).perform
    reset_session
    sign_in_portal_contact(contact)
    redirect_to after_login_path(params[:return_to])
  rescue PortalCustomers::JwtLoginService::Error => e
    Rails.logger.warn("[portal-cliente] SSO JWT recusado no portal #{@portal.id}: #{e.message}")
    @sso_error = true
    render :new, status: :unauthorized
  end

  def destroy
    sign_out_portal_contact
    reset_session
    redirect_to public_portal_locale_path(@portal.slug, @locale)
  end

  private

  def magic_link_service
    @magic_link_service ||= PortalCustomers::MagicLinkService.new(portal: @portal)
  end

  def after_login_path(return_to)
    safe_portal_return_to(return_to) || portal_customer_requests_path(@portal.slug, @locale)
  end

  # Login remoto (Zendesk: "URL de login remoto" do SSO). Ex.: https://hub.b2breservas.com.br/sso/servicedesk
  def remote_login_url
    base = @portal.customer_portal['sso_login_url'].to_s
    return if base.blank? || !base.start_with?('https://')

    target = "#{request.base_url}#{safe_portal_return_to(params[:return_to]) || public_portal_locale_path(@portal.slug, @locale)}"
    separator = base.include?('?') ? '&' : '?'
    "#{base}#{separator}return_to=#{CGI.escape(target)}"
  end
end
