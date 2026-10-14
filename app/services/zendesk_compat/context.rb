# Contexto de uma requisição da API de compatibilidade: conta, usuário autenticado, base das URLs devolvidas
# (respeita o prefixo "/<subdominio>.zendesk.com" quando o n8n usa o subdomínio como caminho) e caches.
class ZendeskCompat::Context
  attr_reader :account, :user, :api_base

  def initialize(account:, user:, api_base:)
    @account = account
    @user = user
    @api_base = api_base.to_s.chomp('/')
  end

  def directory
    @directory ||= ZendeskCompat::Directory.new(account)
  end

  def fields
    @fields ||= ZendeskCompat::FieldTranslator.new(account)
  end

  def api_url(path)
    "#{api_base}/#{path}"
  end

  def time(value)
    value&.utc&.iso8601
  end

  def blob_url(blob)
    Rails.application.routes.url_helpers.rails_blob_url(blob, **url_options)
  end

  def company(contact)
    return if contact&.company_id.blank?

    @companies ||= {}
    @companies[contact.company_id] ||= account.companies.find_by(id: contact.company_id)
  end

  def account_user(user)
    @account_users ||= account.account_users.index_by(&:user_id)
    @account_users[user.id]
  end

  private

  def url_options
    options = Rails.application.routes.default_url_options.presence
    options || { host: ENV.fetch('FRONTEND_URL', 'http://localhost:3000') }
  end
end
