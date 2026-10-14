# Autenticação da API de compatibilidade (M7). Aceita o que a credencial "Zendesk API" do n8n e os clientes da API
# do Zendesk mandam, sempre validando um token de acesso do ServiceDesk (access_tokens, dono = User):
#   Authorization: Basic base64("<email>/token:<token>")   (n8n zendeskApi: e-mail + "API Token")
#   Authorization: Basic base64("<qualquer-id>:<token>")    (credencial Basic genérica, ex.: Sunshine key id:secret)
#   Authorization: Bearer <token>   ou   api_access_token: <token>
# Com e-mail no usuário do Basic, o e-mail precisa ser o do dono do token. Senha de login nunca é aceita.
class ZendeskCompat::Authenticator
  def initialize(request)
    @request = request
  end

  def user
    token, email = credentials
    return if token.blank?

    access_token = AccessToken.find_by(token: token)
    owner = access_token&.owner
    return unless owner.is_a?(User)
    return if email.present? && owner.email.to_s.casecmp(email).nonzero?

    owner
  end

  private

  def credentials
    scheme, value = @request.authorization.to_s.split(' ', 2)
    return basic_credentials(value) if scheme&.casecmp?('Basic')
    return [value.to_s.strip, nil] if scheme&.casecmp?('Bearer')

    [@request.headers['api_access_token'].presence || @request.headers['HTTP_API_ACCESS_TOKEN'], nil]
  end

  def basic_credentials(value)
    decoded = Base64.decode64(value.to_s)
    login, secret = decoded.split(':', 2)
    return [nil, nil] if secret.blank?

    email = login.to_s.delete_suffix('/token')
    [secret, email.include?('@') ? email : nil]
  end
end
