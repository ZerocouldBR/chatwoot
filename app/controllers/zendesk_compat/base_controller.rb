# Base da camada de compatibilidade com a API do Zendesk (M7, docs/ZENDESK-COMPAT-API.md).
# Autenticação como no Zendesk e na credencial "Zendesk API" do n8n:
#   Basic base64("<email>/token:<token>")  -> token de acesso (Perfil > Token de acesso) do usuário com esse e-mail
#   Bearer <token> ou cabeçalho api_access_token -> token de acesso de um usuário
# O usuário precisa ser administrador da conta (usuário de integração; papéis mais finos virão com o M13).
# Conta: ZENDESK_COMPAT_ACCOUNT_ID ou a única conta do usuário. Desligada por padrão: ZENDESK_COMPAT_ENABLED=true.
class ZendeskCompat::BaseController < ActionController::API
  wrap_parameters false

  PER_PAGE_DEFAULT = 100
  PER_PAGE_MAX = 100

  before_action :ensure_enabled!
  before_action :authenticate!
  around_action :with_audit_context

  rescue_from ZendeskCompat::Error, with: :render_compat_error
  rescue_from ActiveRecord::RecordNotFound, with: :render_not_found
  rescue_from ActiveRecord::RecordInvalid, with: :render_record_invalid
  rescue_from ActionController::BadRequest, ActionDispatch::Http::Parameters::ParseError, with: :render_bad_request

  private

  attr_reader :context

  def ensure_enabled!
    return if ActiveModel::Type::Boolean.new.cast(ENV.fetch('ZENDESK_COMPAT_ENABLED', false))

    render json: { error: 'InvalidEndpoint', description: 'Not found' }, status: :not_found
  end

  def authenticate!
    user = ZendeskCompat::Authenticator.new(request).user
    return render_unauthorized if user.nil?

    account = resolve_account(user)
    return render_forbidden if account.nil?

    account_user = account.account_users.find_by(user_id: user.id)
    return render_forbidden unless account_user&.administrator?

    set_current(user, account, account_user)
  end

  def resolve_account(user)
    configured = ENV.fetch('ZENDESK_COMPAT_ACCOUNT_ID', nil).presence
    return user.accounts.find_by(id: configured) if configured

    accounts = user.accounts.to_a
    accounts.size == 1 ? accounts.first : nil
  end

  def set_current(user, account, account_user)
    Current.user = user
    Current.account = account
    Current.account_user = account_user
    Current.executed_by = user
    @context = ZendeskCompat::Context.new(account: account, user: user, api_base: api_base)
  end

  def with_audit_context(&)
    Servicedesk::TicketAuditContext.with('api', &)
  ensure
    Current.reset
  end

  # Base das URLs devolvidas (next_page, url): mantém o prefixo "/<subdominio>.zendesk.com" se a chamada veio por ele.
  def api_base
    prefix = params[:zd_host].present? ? "/#{params[:zd_host]}" : ''
    "#{request.base_url}#{prefix}/api/v2"
  end

  def current_account
    context.account
  end

  def find_ticket!(id = params[:ticket_id] || params[:id])
    display_id = ZendeskCompat::Ids.integer(id)
    conversation = display_id && current_account.conversations.find_by(display_id: display_id)
    conversation || raise(ZendeskCompat::Error::NotFound)
  end

  # Corpo JSON como Hash simples (o Zendesk recebe objetos livres: ticket, comment, custom_fields...).
  def body_params
    @body_params ||= request.request_parameters.to_h.deep_dup
  end

  # Paginação por offset do Zendesk: page / per_page (máx. 100), next_page / previous_page como URL completa.
  def paginate(scope_or_array)
    per_page = params[:per_page].to_i.clamp(1, PER_PAGE_MAX)
    per_page = PER_PAGE_DEFAULT if params[:per_page].blank?
    page = [params[:page].to_i, 1].max
    total = scope_or_array.respond_to?(:count) ? scope_or_array.count : scope_or_array.size
    records = if scope_or_array.is_a?(Array)
                scope_or_array.slice((page - 1) * per_page,
                                     per_page) || []
              else
                scope_or_array.offset((page - 1) * per_page).limit(per_page).to_a
              end
    [records, page_links(page, per_page, total)]
  end

  def page_links(page, per_page, total)
    {
      next_page: page * per_page < total ? page_url(page: page + 1, per_page: per_page) : nil,
      previous_page: page > 1 ? page_url(page: page - 1, per_page: per_page) : nil,
      count: total
    }
  end

  def page_url(overrides)
    query = request.query_parameters.except('page', 'per_page').merge(overrides.stringify_keys)
    "#{request.base_url}#{request.path}?#{query.to_query}"
  end

  def render_unauthorized
    response.headers['WWW-Authenticate'] = 'Basic realm="Web Password"'
    render json: { error: "Couldn't authenticate you" }, status: :unauthorized
  end

  def render_forbidden
    description = 'You do not have access to this page. Please contact the account owner of this help desk for further help.'
    render json: { error: 'Forbidden', description: description }, status: :forbidden
  end

  def render_compat_error(error)
    render json: error.body, status: error.status
  end

  def render_not_found(_error = nil)
    render json: { error: 'RecordNotFound', description: 'Not found' }, status: :not_found
  end

  def render_record_invalid(error)
    details = error.record.errors.to_hash.transform_values { |messages| messages.map { |m| { description: m, error: 'InvalidValue' } } }
    render json: { error: 'RecordInvalid', description: 'Record validation errors', details: details }, status: :unprocessable_entity
  end

  def render_bad_request(error)
    render json: { error: 'InvalidParameter', description: error.message }, status: :bad_request
  end
end
