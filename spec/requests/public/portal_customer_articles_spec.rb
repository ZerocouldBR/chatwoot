require 'rails_helper'

# ServiceDesk B2B: artigos restritos por segmento (equivalente aos user segments do Zendesk Guide).
RSpec.describe 'Portal do cliente: artigos restritos', type: :request do
  # host www.example.com = domínio do helpdesk (sem custom_domain no portal)
  around { |example| with_modified_env(HELPCENTER_URL: 'http://www.example.com') { example.run } }

  let!(:account) { create(:account) }
  let!(:agent) { create(:user, account: account, role: :administrator) }
  let!(:portal) do
    create(:portal, account: account, slug: 'central-b2b',
                    config: { allowed_locales: ['pt_BR'], default_locale: 'pt_BR', customer_portal: { enabled: true } })
  end
  let!(:category) { create(:category, portal: portal, account_id: account.id, locale: 'pt_BR', slug: 'hospitality', name: 'Hospitality') }
  # segmentos do Zendesk: usuários conectados, organização (Accor), tag e equipe
  let!(:segments) do
    accor = sd_create_company(account, name: 'Accor')
    {
      signed_in: PortalUserSegment.create!(account: account, portal: portal, name: 'Usuários conectados'),
      accor: PortalUserSegment.create!(account: account, portal: portal, name: 'Accor', company_ids: [accor]),
      vip: PortalUserSegment.create!(account: account, portal: portal, name: 'Rede VIP', tags: ['vip']),
      staff: PortalUserSegment.create!(account: account, portal: portal, name: 'Agentes', user_type: :staff),
      accor_company: accor
    }
  end
  let!(:articles) do
    {
      public: create_article('Artigo publico liberado'),
      signed_in: create_article('Artigo para conectados', segments[:signed_in]),
      accor: create_article('Artigo exclusivo Accor', segments[:accor]),
      vip: create_article('Artigo da rede vip', segments[:vip]),
      staff: create_article('Artigo interno da equipe', segments[:staff]),
      draft: create_article('Rascunho secreto', nil, status: :draft)
    }
  end
  let!(:accor_contact) { create(:contact, :with_email, account: account, name: 'Cliente Accor', company_id: segments[:accor_company]) }
  let!(:other_contact) do
    create(:contact, :with_email, account: account, name: 'Cliente Outra', company_id: sd_create_company(account, name: 'Outra'))
  end

  def create_article(title, segment = nil, status: :published)
    create(:article, portal: portal, account: account, author: agent, category: category, locale: 'pt_BR',
                     title: title, content: "Conteúdo de #{title}", status: status, portal_user_segment: segment)
  end

  def article_titles_from_json
    response.parsed_body['payload'].pluck('title')
  end

  describe 'visitante anônimo' do
    it 'vê só os artigos sem segmento na lista JSON (busca do portal)' do
      get "/hc/#{portal.slug}/pt_BR/articles.json"
      expect(response).to have_http_status(:ok)
      expect(article_titles_from_json).to contain_exactly('Artigo publico liberado')
    end

    it 'não acha artigo restrito na busca' do
      get "/hc/#{portal.slug}/pt_BR/search", params: { query: 'Artigo' }
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Artigo publico liberado')
      expect(response.body).not_to include('Artigo para conectados', 'Artigo exclusivo Accor', 'Artigo interno da equipe')
    end

    it 'não vê artigo restrito na página inicial nem na categoria' do
      get "/hc/#{portal.slug}/pt_BR"
      expect(response.body).not_to include('Artigo para conectados', 'Artigo exclusivo Accor')
      get "/hc/#{portal.slug}/pt_BR/categories/#{category.slug}"
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Artigo publico liberado')
      expect(response.body).not_to include('Artigo para conectados', 'Artigo exclusivo Accor', 'Artigo interno da equipe')
    end

    it 'é levado ao login ao abrir artigo restrito e não recebe o conteúdo' do
      get "/hc/#{portal.slug}/articles/#{articles[:signed_in].slug}"
      expect(response).to redirect_to(%r{/hc/central-b2b/pt_BR/login\?return_to=})
      expect(response.body).not_to include('Conteúdo de Artigo para conectados')
    end

    it 'recebe 404 no markdown do artigo restrito' do
      get "/hc/#{portal.slug}/articles/#{articles[:signed_in].slug}.md"
      expect(response).to have_http_status(:not_found)
    end

    it 'não lista artigo restrito no sitemap' do
      get "/hc/#{portal.slug}/sitemap.xml"
      expect(response.body).to include(articles[:public].slug)
      expect(response.body).not_to include(articles[:signed_in].slug)
    end

    it 'recebe 404 em rascunho no portal do cliente, salvo com o token de pré-visualização do painel' do
      get "/hc/#{portal.slug}/articles/#{articles[:draft].slug}"
      expect(response).to have_http_status(:not_found)

      token = Rails.application.message_verifier(:sd_article_preview).generate(articles[:draft].id, purpose: :preview, expires_in: 1.hour)
      get "/hc/#{portal.slug}/articles/#{articles[:draft].slug}", params: { preview_token: token }
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Conteúdo de Rascunho secreto')

      other_token = Rails.application.message_verifier(:sd_article_preview).generate(articles[:public].id, purpose: :preview)
      get "/hc/#{portal.slug}/articles/#{articles[:draft].slug}", params: { preview_token: other_token }
      expect(response).to have_http_status(:not_found)
    end
  end

  describe 'contato logado' do
    it 'vê os artigos de "usuários conectados" e os da própria organização, nunca os da equipe' do
      sd_sign_in(portal, accor_contact)
      get "/hc/#{portal.slug}/pt_BR/articles.json"
      expect(article_titles_from_json).to contain_exactly('Artigo publico liberado', 'Artigo para conectados', 'Artigo exclusivo Accor')

      get "/hc/#{portal.slug}/articles/#{articles[:accor].slug}"
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Conteúdo de Artigo exclusivo Accor')

      get "/hc/#{portal.slug}/articles/#{articles[:staff].slug}"
      expect(response).to have_http_status(:not_found)
    end

    it 'de outra organização recebe 404 no artigo da Accor' do
      sd_sign_in(portal, other_contact)
      get "/hc/#{portal.slug}/articles/#{articles[:accor].slug}"
      expect(response).to have_http_status(:not_found)
      get "/hc/#{portal.slug}/pt_BR/articles.json"
      expect(article_titles_from_json).to contain_exactly('Artigo publico liberado', 'Artigo para conectados')
    end

    it 'com a etiqueta do segmento (tag do Zendesk) vê o artigo da tag' do
      other_contact.update!(label_list: ['vip'])
      sd_sign_in(portal, other_contact)
      get "/hc/#{portal.slug}/articles/#{articles[:vip].slug}"
      expect(response).to have_http_status(:ok)
    end

    it 'perde o acesso na hora se for bloqueado' do
      sd_sign_in(portal, accor_contact)
      accor_contact.update!(blocked: true)
      get "/hc/#{portal.slug}/articles/#{articles[:signed_in].slug}"
      expect(response).to have_http_status(:redirect)
    end
  end

  describe '"Exigir login" (require_sign_in)' do
    before { portal.update!(config: portal.config.merge('customer_portal' => { 'enabled' => true, 'require_sign_in' => true })) }

    it 'manda o anônimo para o login em todas as páginas e nega o JSON' do
      get "/hc/#{portal.slug}/pt_BR"
      expect(response).to redirect_to(%r{/hc/central-b2b/pt_BR/login})
      get "/hc/#{portal.slug}/articles/#{articles[:public].slug}"
      expect(response).to redirect_to(%r{/login})
      get "/hc/#{portal.slug}/pt_BR/articles.json"
      expect(response).to have_http_status(:unauthorized)
      get "/hc/#{portal.slug}/sitemap.xml"
      expect(response.body).not_to include(articles[:public].slug)
    end

    it 'libera a Central depois do login' do
      sd_sign_in(portal, accor_contact)
      get "/hc/#{portal.slug}/pt_BR"
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Minhas atividades', 'Hospitality')
    end
  end

  describe 'portal sem o portal do cliente ligado' do
    before { portal.update!(config: { 'customer_portal' => { 'enabled' => false } }) }

    it 'continua escondendo artigo restrito e não oferece login' do
      get "/hc/#{portal.slug}/articles/#{articles[:signed_in].slug}"
      expect(response).to have_http_status(:not_found)
      get "/hc/#{portal.slug}/pt_BR/login"
      expect(response).to have_http_status(:not_found)
    end
  end

  it 'não aceita segmento de outro portal no artigo' do
    segment = PortalUserSegment.create!(account: account, portal: create(:portal, account: account), name: 'Outro')
    expect(build(:article, portal: portal, account: account, author: agent, portal_user_segment: segment)).not_to be_valid
  end
end
