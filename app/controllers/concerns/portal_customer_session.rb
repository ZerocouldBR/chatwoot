# ServiceDesk B2B: sessão do contato (usuário final) no portal da Central de Ajuda.
#
# A sessão fica num cookie criptografado e assinado (cookies.encrypted), por portal, com validade de
# SESSION_TTL. O cookie guarda o id e o e-mail do contato: se o contato for bloqueado, apagado ou trocar
# de e-mail, a sessão deixa de valer na hora. O login é feito por link mágico ou SSO JWT
# (Public::Api::V1::Portals::CustomerSessionsController).
module PortalCustomerSession
  extend ActiveSupport::Concern

  SESSION_TTL = 12.hours

  included do
    helper_method :portal_contact, :portal_contact_signed_in?, :portal_visible_segment_ids, :customer_portal_enabled?,
                  :portal_customer_locale
  end

  private

  def portal_cookie_name
    "sd_hc_#{@portal.id}"
  end

  def customer_portal_enabled?
    @portal.present? && @portal.customer_portal_enabled?
  end

  def portal_contact
    return @portal_contact if defined?(@portal_contact)

    @portal_contact = load_portal_contact
  end

  def portal_contact_signed_in?
    portal_contact.present?
  end

  def load_portal_contact
    data = portal_session_data
    return if data.blank?

    contact = @portal.account.contacts.find_by(id: data['contact_id'])
    contact if session_contact_valid?(contact, data)
  end

  def portal_session_data
    return if @portal.blank? || !@portal.customer_portal_enabled?

    data = cookies.encrypted[portal_cookie_name]
    return unless data.is_a?(Hash)

    data if data['portal_id'] == @portal.id && data['exp'].to_i > Time.current.to_i
  end

  def session_contact_valid?(contact, data)
    contact.present? && !contact.blocked? && contact.email.present? && contact.email.casecmp?(data['email'].to_s)
  end

  def sign_in_portal_contact(contact)
    expires_at = SESSION_TTL.from_now
    cookies.encrypted[portal_cookie_name] = {
      value: { 'contact_id' => contact.id, 'portal_id' => @portal.id, 'email' => contact.email, 'exp' => expires_at.to_i },
      expires: expires_at, httponly: true, same_site: :lax, secure: request.ssl?, path: '/'
    }
    @portal_contact = contact
    @portal_visible_segment_ids = nil
  end

  def sign_out_portal_contact
    cookies.delete(portal_cookie_name, path: '/')
    @portal_contact = nil
    @portal_visible_segment_ids = nil
  end

  # Segmentos que o visitante atual pode ver (anônimo: nenhum).
  def portal_visible_segment_ids
    @portal_visible_segment_ids ||= PortalUserSegment.visible_ids_for(@portal, portal_contact)
  end

  def portal_customer_locale
    @locale.presence || params[:locale].presence || @portal&.default_locale
  end

  # "Exigir login" (Zendesk Guide): sem sessão, toda a Central redireciona para o login.
  def enforce_portal_sign_in
    return if @portal.blank? || !@portal.require_sign_in? || portal_contact_signed_in?
    return head(:unauthorized) unless request.format.html?

    redirect_to portal_customer_login_path(@portal.slug, portal_customer_locale, return_to: request.fullpath)
  end

  def require_portal_contact!
    return if portal_contact_signed_in?

    redirect_to portal_customer_login_path(@portal.slug, portal_customer_locale, return_to: request.fullpath)
  end

  def ensure_customer_portal_enabled!
    render_404 unless customer_portal_enabled?
  end

  # Só aceita caminho relativo do próprio portal (evita open redirect).
  def safe_portal_return_to(value)
    path = value.to_s
    base = "/hc/#{@portal.slug}"
    return unless path == base || path.start_with?("#{base}/", "#{base}?")
    return if path.include?('//') || path.include?('\\') || path.match?(/[\r\n]/)

    path
  end
end
