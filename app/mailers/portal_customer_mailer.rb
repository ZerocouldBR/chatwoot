# ServiceDesk B2B: e-mail com o link de acesso do usuário final à Central de Ajuda (link mágico).
# Só é chamado quando SD_PORTAL_LOGIN_EMAIL_ENABLED=true (ver PortalCustomers::MagicLinkService).
class PortalCustomerMailer < ApplicationMailer
  def magic_link(contact, portal, url, locale)
    return unless smtp_config_set_or_development?

    @contact = contact
    @portal = portal
    @action_url = url
    @ttl_minutes = PortalCustomers::MagicLinkService::TOKEN_TTL.in_minutes.to_i
    I18n.with_locale(mailer_locale(locale)) do
      send_mail_with_liquid(to: contact.email, subject: I18n.t('public_portal.sd.login.email.subject', portal: portal_name))
    end
  end

  private

  def portal_name
    @portal.display_title.presence || @portal.name
  end

  def mailer_locale(locale)
    candidate = locale.to_s.tr('-', '_')
    I18n.available_locales.map(&:to_s).include?(candidate) ? candidate : I18n.locale
  end

  def liquid_locals
    super.merge(
      contact_name: @contact.name.presence || @contact.email,
      portal_name: portal_name,
      ttl_minutes: @ttl_minutes,
      greeting: I18n.t('public_portal.sd.login.email.greeting', name: @contact.name.presence || @contact.email),
      intro: I18n.t('public_portal.sd.login.email.intro', portal: portal_name),
      button: I18n.t('public_portal.sd.login.email.button'),
      expiry: I18n.t('public_portal.sd.login.email.expiry', minutes: @ttl_minutes),
      ignore: I18n.t('public_portal.sd.login.email.ignore')
    )
  end
end
