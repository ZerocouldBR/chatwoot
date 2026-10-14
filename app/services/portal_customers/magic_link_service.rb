# ServiceDesk B2B: login do contato no portal por link mágico (sem senha).
#
# - request!(email): se existir contato com esse e-mail na conta do portal (e não bloqueado), gera um token
#   aleatório de 32 bytes, guarda no Redis só o SHA-256 dele (validade TOKEN_TTL) e envia o link por e-mail.
#   A resposta para quem pediu é sempre a mesma (não revela se o e-mail existe).
#   Um mesmo e-mail só recebe um link a cada RESEND_COOLDOWN (evita bombardeio de e-mails).
# - consume!(token): devolve o contato e apaga o token (uso único). Token vencido, usado ou de outro portal
#   devolve nil.
#
# Envio dormente: o e-mail só sai com SD_PORTAL_LOGIN_EMAIL_ENABLED=true (na demo fica desligado).
class PortalCustomers::MagicLinkService
  TOKEN_TTL = 20.minutes
  RESEND_COOLDOWN = 60.seconds
  KEY_PREFIX = 'SD_PORTAL_LOGIN'.freeze

  Result = Struct.new(:status, :contact, :url, keyword_init: true)

  pattr_initialize [:portal!]

  def self.email_delivery_enabled?
    ActiveModel::Type::Boolean.new.cast(ENV.fetch('SD_PORTAL_LOGIN_EMAIL_ENABLED', false)) == true
  end

  def request!(email:, locale:, return_to: nil, base_url: nil)
    contact = find_contact(email)
    return Result.new(status: :unknown) if contact.blank?
    return Result.new(status: :cooldown, contact: contact) unless claim_cooldown(contact)

    token = SecureRandom.urlsafe_base64(32)
    Redis::Alfred.set(token_key(token), { contact_id: contact.id, portal_id: portal.id, return_to: return_to }.to_json,
                      ex: TOKEN_TTL.to_i)
    url = verify_url(token, locale, base_url)
    deliver(contact, url, locale)
    Result.new(status: :sent, contact: contact, url: url)
  end

  def consume!(token)
    return if token.blank? || token.length > 128

    data = parse_token_data(take_once(token_key(token)))
    return unless data && data['portal_id'] == portal.id

    contact = portal.account.contacts.find_by(id: data['contact_id'])
    [contact, data['return_to']] if contact.present? && !contact.blocked?
  end

  # Só lê (sem consumir) para a página de confirmação.
  def valid_token?(token)
    token.present? && token.length <= 128 && Redis::Alfred.exists?(token_key(token))
  end

  private

  def parse_token_data(raw)
    raw.present? ? JSON.parse(raw) : nil
  rescue JSON::ParserError
    nil
  end

  # GET + DEL: só quem apagar a chave (DEL = 1) usa o token, mesmo com dois cliques ao mesmo tempo.
  def take_once(key)
    Redis::Alfred.with do |conn|
      value = conn.get(key)
      value if value.present? && conn.del(key).to_i == 1
    end
  end

  def find_contact(email)
    normalized = email.to_s.strip.downcase
    return if normalized.blank? || normalized.length > 254 || !normalized.match?(URI::MailTo::EMAIL_REGEXP)

    contact = portal.account.contacts.from_email(normalized)
    contact if contact.present? && !contact.blocked?
  end

  def claim_cooldown(contact)
    Redis::Alfred.set("#{KEY_PREFIX}:COOLDOWN:#{portal.id}:#{contact.id}", '1', nx: true, ex: RESEND_COOLDOWN.to_i)
  end

  def token_key(token)
    "#{KEY_PREFIX}:TOKEN:#{Digest::SHA256.hexdigest(token)}"
  end

  def verify_url(token, locale, base_url)
    base = base_url.presence || ENV.fetch('FRONTEND_URL', '')
    "#{base.chomp('/')}/hc/#{portal.slug}/#{locale}/login/verify?token=#{token}"
  end

  def deliver(contact, url, locale)
    unless self.class.email_delivery_enabled?
      Rails.logger.info("[portal-cliente] link de acesso gerado para o contato #{contact.id} (envio de e-mail dormente)")
      return
    end

    PortalCustomerMailer.with(account: portal.account).magic_link(contact, portal, url, locale).deliver_later
  end
end
