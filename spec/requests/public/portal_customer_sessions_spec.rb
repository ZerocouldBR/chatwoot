require 'rails_helper'

# ServiceDesk B2B: login do usuário final na Central de Ajuda (link mágico e SSO JWT no formato do Zendesk).
RSpec.describe 'Portal do cliente: login do contato', type: :request do
  # host www.example.com = domínio do helpdesk (sem custom_domain no portal)
  around { |example| with_modified_env(HELPCENTER_URL: 'http://www.example.com') { example.run } }

  let!(:account) { create(:account) }
  let!(:portal) do
    create(:portal, account: account, slug: 'central-b2b',
                    config: { allowed_locales: ['pt_BR'], default_locale: 'pt_BR', customer_portal: { enabled: true } })
  end
  let!(:contact) { create(:contact, account: account, name: 'Ana Agência', email: 'ana@agencia.com.br') }
  let(:login_path) { "/hc/#{portal.slug}/pt_BR/login" }
  let(:verify_path) { "/hc/#{portal.slug}/pt_BR/login/verify" }
  let(:requests_path) { "/hc/#{portal.slug}/pt_BR/requests" }

  before { Redis::Alfred.delete("#{PortalCustomers::MagicLinkService::KEY_PREFIX}:COOLDOWN:#{portal.id}:#{contact.id}") }

  describe 'link mágico' do
    it 'mostra o formulário de e-mail' do
      get login_path
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Acesse a Central de Ajuda', 'name="email"')
    end

    it 'responde igual para e-mail cadastrado e desconhecido (não revela quem é cliente)' do
      post login_path, params: { email: 'ana@agencia.com.br' }
      known = response.body.scan('Verifique seu e-mail').size
      post login_path, params: { email: 'ninguem@exemplo.com' }
      expect(response).to have_http_status(:ok)
      expect(response.body.scan('Verifique seu e-mail').size).to eq(known)
      expect(known).to eq(1)
    end

    it 'não envia e-mail com o envio dormente e envia quando SD_PORTAL_LOGIN_EMAIL_ENABLED=true' do
      expect do
        post login_path, params: { email: contact.email }
      end.not_to have_enqueued_job(ActionMailer::MailDeliveryJob)
      expect(response.body).to include('O envio de e-mails está desligado')

      Redis::Alfred.delete("#{PortalCustomers::MagicLinkService::KEY_PREFIX}:COOLDOWN:#{portal.id}:#{contact.id}")
      with_modified_env SD_PORTAL_LOGIN_EMAIL_ENABLED: 'true' do
        expect do
          post login_path, params: { email: contact.email }
        end.to have_enqueued_job(ActionMailer::MailDeliveryJob)
      end
    end

    it 'gera o e-mail com o link de acesso' do
      url = 'https://helpdesk.example/hc/x/pt_BR/login/verify?token=abc'
      mail = PortalCustomerMailer.with(account: account).magic_link(contact, portal, url, 'pt_BR')
      expect(mail.to).to eq([contact.email])
      expect(mail.subject).to include('Seu link de acesso')
      expect(mail.body.encoded).to include('https://helpdesk.example/hc/x/pt_BR/login/verify?token=abc')
    end

    it 'só envia um link por minuto para o mesmo e-mail' do
      service = PortalCustomers::MagicLinkService.new(portal: portal)
      expect(service.request!(email: contact.email, locale: 'pt_BR').status).to eq(:sent)
      expect(service.request!(email: contact.email, locale: 'pt_BR').status).to eq(:cooldown)
    end

    it 'não gera link para contato bloqueado nem de outra conta' do
      contact.update!(blocked: true)
      expect(PortalCustomers::MagicLinkService.new(portal: portal).request!(email: contact.email, locale: 'pt_BR').status).to eq(:unknown)

      other = create(:contact, account: create(:account), email: 'outro@cliente.com')
      expect(PortalCustomers::MagicLinkService.new(portal: portal).request!(email: other.email, locale: 'pt_BR').status).to eq(:unknown)
    end

    it 'a página do link não consome o token; o POST consome e cria a sessão (uso único)' do
      token = sd_magic_link_token(portal, contact)
      get verify_path, params: { token: token }
      expect(response).to have_http_status(:ok)
      get verify_path, params: { token: token }
      expect(response).to have_http_status(:ok)

      post verify_path, params: { token: token }
      expect(response).to redirect_to(requests_path)
      get requests_path
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Ana Agência')

      post verify_path, params: { token: token }
      expect(response).to have_http_status(:unprocessable_entity)
      expect(response.body).to include('Link inválido ou expirado')
    end

    it 'confirma com o CSRF do Rails ligado (página não usa no-referrer, que zera o Origin)' do
      token = sd_magic_link_token(portal, contact)
      ActionController::Base.allow_forgery_protection = true
      get verify_path, params: { token: token }
      expect(response.body).to include('content="same-origin"')
      expect(response.body).not_to include('no-referrer')
      csrf = response.body[/name="authenticity_token" value="([^"]+)"/, 1]
      post verify_path, params: { token: token, authenticity_token: csrf }, headers: { 'Origin' => 'http://www.example.com' }
      expect(response).to redirect_to(requests_path)
    ensure
      ActionController::Base.allow_forgery_protection = false
    end

    it 'recusa token inventado ou vencido' do
      post verify_path, params: { token: 'inventado' }
      expect(response).to have_http_status(:unprocessable_entity)

      token = sd_magic_link_token(portal, contact)
      travel_to(PortalCustomers::MagicLinkService::TOKEN_TTL.from_now + 1.minute) do
        Redis::Alfred.delete("SD_PORTAL_LOGIN:TOKEN:#{Digest::SHA256.hexdigest(token)}") # o Redis expira sozinho
        post verify_path, params: { token: token }
        expect(response).to have_http_status(:unprocessable_entity)
      end
    end

    it 'recusa token de outro portal' do
      other_portal = create(:portal, account: account, slug: 'outro',
                                     config: { allowed_locales: ['pt_BR'], default_locale: 'pt_BR', customer_portal: { enabled: true } })
      token = sd_magic_link_token(other_portal, contact)
      post verify_path, params: { token: token }
      expect(response).to have_http_status(:unprocessable_entity)
    end

    it 'volta para o caminho pedido, mas ignora destino externo (open redirect)' do
      token = sd_magic_link_token(portal, contact, return_to: "/hc/#{portal.slug}/pt_BR/requests/new")
      post verify_path, params: { token: token }
      expect(response).to redirect_to("/hc/#{portal.slug}/pt_BR/requests/new")

      delete "/hc/#{portal.slug}/pt_BR/logout"
      %w[https://evil.example //evil.example /hc/central-b2b//evil.example /hc/outro-portal/pt_BR].each do |target|
        Redis::Alfred.delete("#{PortalCustomers::MagicLinkService::KEY_PREFIX}:COOLDOWN:#{portal.id}:#{contact.id}")
        post login_path, params: { email: contact.email, return_to: target }
        get login_path, params: { return_to: target }
        expect(response.body).not_to include('evil.example')
      end
    end

    it 'sair apaga a sessão' do
      sd_sign_in(portal, contact)
      delete "/hc/#{portal.slug}/pt_BR/logout"
      expect(response).to redirect_to("/hc/#{portal.slug}/pt_BR")
      get requests_path
      expect(response).to redirect_to(%r{/login})
    end

    it 'cookie de sessão de um portal não vale em outro' do
      sd_sign_in(portal, contact)
      other_portal = create(:portal, account: account, slug: 'outro-portal',
                                     config: { allowed_locales: ['pt_BR'], default_locale: 'pt_BR', customer_portal: { enabled: true } })
      get "/hc/#{other_portal.slug}/pt_BR/requests"
      expect(response).to redirect_to(%r{/hc/outro-portal/pt_BR/login})
    end

    it 'redireciona o login para o HUB quando há login remoto configurado' do
      portal.update!(config: portal.config.merge('customer_portal' => { 'enabled' => true,
                                                                        'sso_login_url' => 'https://hub.b2breservas.com.br/sso/servicedesk' }))
      get login_path
      expect(response).to redirect_to(%r{\Ahttps://hub\.b2breservas\.com\.br/sso/servicedesk\?return_to=})
      get login_path, params: { local: '1' }
      expect(response).to have_http_status(:ok)
    end
  end

  describe 'SSO JWT (HUB, formato do Zendesk)' do
    let(:secret) { 'segredo-de-teste-com-mais-de-32-caracteres' }
    let(:sso_path) { "/hc/#{portal.slug}/pt_BR/sso/jwt" }

    def jwt_for(key: secret, **claims)
      JWT.encode({ iat: Time.current.to_i, jti: SecureRandom.uuid }.merge(claims), key, 'HS256')
    end

    it 'fica desligado sem SD_PORTAL_JWT_SECRET' do
      with_modified_env SD_PORTAL_JWT_SECRET: '' do
        get sso_path, params: { jwt: jwt_for(email: contact.email) }
        expect(response).to have_http_status(:unauthorized)
      end
    end

    it 'entra com token válido, recusa reuso, assinatura errada e token velho' do
      with_modified_env SD_PORTAL_JWT_SECRET: secret do
        token = jwt_for(email: 'ANA@agencia.com.br', name: 'Ana')
        get sso_path, params: { jwt: token, return_to: "/hc/#{portal.slug}/pt_BR/requests/new" }
        expect(response).to redirect_to("/hc/#{portal.slug}/pt_BR/requests/new")

        delete "/hc/#{portal.slug}/pt_BR/logout"
        get sso_path, params: { jwt: token }
        expect(response).to have_http_status(:unauthorized)

        get sso_path, params: { jwt: jwt_for(email: contact.email, key: 'outra-chave-com-mais-de-32-caracteres!!') }
        expect(response).to have_http_status(:unauthorized)

        get sso_path, params: { jwt: jwt_for(email: contact.email, iat: 10.minutes.ago.to_i) }
        expect(response).to have_http_status(:unauthorized)
        get requests_path
        expect(response).to redirect_to(%r{/login})
      end
    end

    it 'cria o contato que ainda não existe, como o Zendesk' do
      with_modified_env SD_PORTAL_JWT_SECRET: secret do
        expect do
          get sso_path, params: { jwt: jwt_for(email: 'novo@hotel.com.br', name: 'Hotel Novo', external_id: 'hub-99') }
        end.to change(account.contacts, :count).by(1)
        created = account.contacts.from_email('novo@hotel.com.br')
        expect(created.name).to eq('Hotel Novo')
        expect(created.additional_attributes['sso_external_id']).to eq('hub-99')
      end
    end
  end
end
