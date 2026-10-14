# ServiceDesk B2B: SSO por JWT, no mesmo formato do "JSON Web Token" do Zendesk.
#
# Hoje o Zendesk da B2B não tem login próprio para o usuário final: a Central redireciona para o HUB
# (hub.b2breservas.com.br/sso/zendesk), que devolve um JWT assinado (HS256) com a chave compartilhada.
# Para o HUB passar a autenticar no ServiceDesk basta trocar a URL de retorno para
#   https://<helpdesk>/hc/<portal>/<locale>/sso/jwt?jwt=<token>&return_to=<caminho>
# e usar a chave de SD_PORTAL_JWT_SECRET. Sem a variável, o SSO fica desligado.
#
# Claims aceitas (as do Zendesk): email (obrigatória), name, external_id, iat (obrigatória, até
# MAX_AGE no passado), jti (obrigatória, uso único), exp (opcional).
# Contato inexistente é criado (como o Zendesk faz), a menos que SD_PORTAL_JWT_CREATE_CONTACTS=false.
class PortalCustomers::JwtLoginService
  MAX_AGE = 3.minutes
  LEEWAY = 30.seconds
  KEY_PREFIX = 'SD_PORTAL_JWT_JTI'.freeze

  class Error < StandardError; end

  pattr_initialize [:portal!, :token!]

  def self.enabled?
    ENV.fetch('SD_PORTAL_JWT_SECRET', '').length >= 32
  end

  def perform
    raise Error, 'sso_disabled' unless self.class.enabled?

    claims = decode
    validate_claims!(claims)
    find_or_create_contact(claims)
  end

  private

  def decode
    payload, = JWT.decode(token, ENV.fetch('SD_PORTAL_JWT_SECRET'), true, algorithm: 'HS256', leeway: LEEWAY.to_i)
    payload
  rescue JWT::DecodeError => e
    raise Error, "invalid_token: #{e.class.name.demodulize}"
  end

  def validate_claims!(claims)
    validate_iat!(claims['iat'].to_i)
    validate_email!(claims['email'])
    validate_jti!(claims['jti'].to_s)
  end

  def validate_iat!(iat)
    now = Time.current.to_i
    raise Error, 'missing_iat' if iat.zero?
    raise Error, 'stale_token' if iat < now - MAX_AGE.to_i || iat > now + LEEWAY.to_i
  end

  def validate_email!(email)
    raise Error, 'invalid_email' unless email.to_s.strip.downcase.match?(URI::MailTo::EMAIL_REGEXP)
  end

  # jti de uso único: o mesmo token não entra duas vezes
  def validate_jti!(jti)
    raise Error, 'missing_jti' if jti.blank? || jti.length > 255

    key = "#{KEY_PREFIX}:#{Digest::SHA256.hexdigest(jti)}"
    raise Error, 'replayed_token' unless Redis::Alfred.set(key, '1', nx: true, ex: (MAX_AGE * 2).to_i)
  end

  def find_or_create_contact(claims)
    email = claims['email'].to_s.strip.downcase
    contact = portal.account.contacts.from_email(email)
    raise Error, 'blocked_contact' if contact&.blocked?
    return contact if contact.present?
    raise Error, 'unknown_contact' unless create_contacts?

    portal.account.contacts.create!(
      email: email, name: claims['name'].presence || email,
      additional_attributes: { 'source' => 'portal_sso', 'sso_external_id' => claims['external_id'].presence }.compact
    )
  end

  def create_contacts?
    ActiveModel::Type::Boolean.new.cast(ENV.fetch('SD_PORTAL_JWT_CREATE_CONTACTS', true)) != false
  end
end
