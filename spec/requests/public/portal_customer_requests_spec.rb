require 'rails_helper'

# ServiceDesk B2B: "Enviar uma solicitação", "Minhas solicitações" e "Solicitações da organização".
RSpec.describe 'Portal do cliente: solicitações', type: :request do
  # host www.example.com = domínio do helpdesk (sem custom_domain no portal)
  around { |example| with_modified_env(HELPCENTER_URL: 'http://www.example.com') { example.run } }

  let!(:account) { create(:account) }
  let!(:api_inbox) { create(:inbox, account: account, name: 'Central de Ajuda', channel: create(:channel_api, account: account)) }
  let!(:portal) do
    create(:portal, account: account, slug: 'central-b2b',
                    config: { allowed_locales: ['pt_BR'], default_locale: 'pt_BR',
                              customer_portal: { enabled: true, request_inbox_id: api_inbox.id } })
  end
  let!(:company) { sd_create_company(account, name: 'Rede Hoteleira', custom_attributes: { portal_shared_requests: true }) }
  let!(:ana) { create(:contact, account: account, name: 'Ana', email: 'ana@rede.com.br') }
  let!(:bruno) { create(:contact, account: account, name: 'Bruno', email: 'bruno@rede.com.br') }
  let!(:carla) { create(:contact, account: account, name: 'Carla', email: 'carla@outra.com.br') }
  let(:base) { "/hc/#{portal.slug}/pt_BR" }

  let!(:ana_ticket) { create_ticket(ana, 'Erro na tarifa do hotel', status: :open, zd_status: 'Aberto') }
  let!(:ana_pending) { create_ticket(ana, 'Aguardando boleto', status: :waiting_on_customer, zd_status: 'Pendente') }
  let!(:ana_closed) { create_ticket(ana, 'Antigo e fechado', status: :closed, zd_status: 'Resolvido', zd_status_sistema: 'Fechado') }

  before do
    [ana, bruno].each { |c| c.update_columns(company_id: company) } # rubocop:disable Rails/SkipsModelValidations
    create_ticket(ana, 'Ajuste no channel', status: :on_hold, zd_status: 'Desenvolvimento')
    create_ticket(bruno, 'Pedido do Bruno', status: :open)
    create_ticket(carla, 'Pedido da Carla', status: :open)
  end

  def create_ticket(contact, subject, status:, zd_status: nil, zd_status_sistema: nil)
    conversation = create(:conversation, account: account, inbox: api_inbox, contact: contact,
                                         additional_attributes: { 'mail_subject' => subject })
    create(:message, conversation: conversation, account: account, inbox: api_inbox, sender: contact, message_type: :incoming,
                     content: "Mensagem inicial: #{subject}")
    create(:message, conversation: conversation, account: account, inbox: api_inbox, message_type: :outgoing,
                     content: 'Nota interna que o cliente não pode ver', private: true)
    # status por último: a mensagem do cliente reabre o ticket
    conversation.update_columns(status: Conversation.statuses[status], # rubocop:disable Rails/SkipsModelValidations
                                custom_attributes: { 'zd_status' => zd_status, 'zd_status_sistema' => zd_status_sistema }.compact)
    conversation.reload
  end

  describe 'acesso' do
    it 'anônimo vai para o login em todas as telas de solicitação' do
      get "#{base}/requests"
      expect(response).to redirect_to(%r{/login\?return_to=})
      get "#{base}/requests/#{ana_ticket.display_id}"
      expect(response).to redirect_to(%r{/login})
      post "#{base}/requests", params: { subject: 'x', description: 'y' }
      expect(response).to redirect_to(%r{/login})
      expect(Conversation.where(inbox: api_inbox).count).to eq(6)
    end

    it 'cliente vê só as próprias solicitações' do
      sd_sign_in(portal, ana)
      get "#{base}/requests"
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Erro na tarifa do hotel', 'Aguardando boleto', 'Antigo e fechado')
      expect(response.body).not_to include('Pedido do Bruno', 'Pedido da Carla')
    end

    it 'cliente recebe 404 no ticket de outro cliente' do
      sd_sign_in(portal, carla)
      get "#{base}/requests/#{ana_ticket.display_id}"
      expect(response).to have_http_status(:not_found)
      post "#{base}/requests/#{ana_ticket.display_id}/comments", params: { content: 'invasão' }
      expect(response).to have_http_status(:not_found)
      expect(ana_ticket.messages.where(content: 'invasão')).to be_empty
    end

    it 'detalhe mostra mensagens públicas e esconde notas internas' do
      sd_sign_in(portal, ana)
      get "#{base}/requests/#{ana_ticket.display_id}"
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Mensagem inicial: Erro na tarifa do hotel', "##{ana_ticket.display_id}")
      expect(response.body).not_to include('Nota interna que o cliente não pode ver')
    end
  end

  describe 'status no padrão Zendesk' do
    it 'mostra o rótulo do usuário final e filtra por Aberto, Aguardando sua resposta e Resolvido' do
      sd_sign_in(portal, ana)
      get "#{base}/requests", params: { status: 'awaiting' }
      expect(response.body).to include('Aguardando boleto', 'Aguardando resposta')
      expect(response.body).not_to include('Ajuste no channel', 'Erro na tarifa do hotel')

      get "#{base}/requests", params: { status: 'open' }
      expect(response.body).to include('Erro na tarifa do hotel', 'Ajuste no channel', 'Desenvolvimento')
      expect(response.body).not_to include('Aguardando boleto', 'Antigo e fechado')

      get "#{base}/requests", params: { status: 'solved' }
      expect(response.body).to include('Antigo e fechado')
      expect(response.body).not_to include('Erro na tarifa do hotel')
    end

    it 'pesquisa pelo assunto e pelo número' do
      sd_sign_in(portal, ana)
      get "#{base}/requests", params: { query: 'tarifa' }
      expect(response.body).to include('Erro na tarifa do hotel')
      expect(response.body).not_to include('Aguardando boleto')
      get "#{base}/requests", params: { query: "##{ana_pending.display_id}" }
      expect(response.body).to include('Aguardando boleto')
    end
  end

  describe 'Solicitações da organização' do
    it 'fica oculta enquanto o portal não liga organization_requests' do
      sd_sign_in(portal, bruno)
      get "#{base}/requests", params: { scope: 'organization' }
      expect(response.body).not_to include('Solicitações da organização', 'Erro na tarifa do hotel')
      get "#{base}/requests/#{ana_ticket.display_id}"
      expect(response).to have_http_status(:not_found)
    end

    context 'when organization_requests is on (organização compartilha)' do
      before do
        portal.update!(config: portal.config.merge('customer_portal' => portal.customer_portal.merge('organization_requests' => true)))
      end

      it 'mostra os tickets da mesma empresa, nunca de outra' do
        sd_sign_in(portal, bruno)
        get "#{base}/requests", params: { scope: 'organization' }
        expect(response.body).to include('Solicitações da organização', 'Erro na tarifa do hotel', 'Pedido do Bruno')
        expect(response.body).not_to include('Pedido da Carla')
        get "#{base}/requests/#{ana_ticket.display_id}"
        expect(response).to have_http_status(:ok)
      end

      it 'não deixa responder no ticket do colega sem portal_shared_comments' do
        sd_sign_in(portal, bruno)
        post "#{base}/requests/#{ana_ticket.display_id}/comments", params: { content: 'Comentário do colega' }
        expect(response).to have_http_status(:forbidden)
        expect(ana_ticket.messages.where(content: 'Comentário do colega')).to be_empty
      end

      it 'empresa que não compartilha não vê os tickets dos colegas' do
        ActiveRecord::Base.connection.execute("UPDATE companies SET custom_attributes = '{}' WHERE id = #{company}")
        sd_sign_in(portal, bruno)
        get "#{base}/requests/#{ana_ticket.display_id}"
        expect(response).to have_http_status(:not_found)
      end

      it 'contato sem empresa não vê a aba' do
        sd_sign_in(portal, carla)
        get "#{base}/requests", params: { scope: 'organization' }
        expect(response.body).not_to include('Solicitações da organização')
      end
    end
  end

  describe 'Enviar uma solicitação' do
    it 'mostra o formulário Atendimento com Assunto, Descrição, CNPJ e anexos' do
      sd_sign_in(portal, carla)
      get "#{base}/requests/new"
      expect(response).to have_http_status(:ok)
      expect(response.body).to include('Enviar uma solicitação', 'name="subject"', 'name="description"', 'name="fields[cnpj]"',
                                       'name="attachments[]"')
    end

    it 'cria o ticket na inbox do portal, com anexo e atributos do Zendesk' do
      sd_sign_in(portal, carla)
      expect do
        post "#{base}/requests", params: {
          form_id: 'atendimento', subject: 'Não consigo emitir a VCN', description: "Passo a passo:\n1. abro o B2B.pay",
          fields: { cnpj: '12.345.678/0001-90' },
          attachments: [fixture_file_upload(Rails.root.join('spec/assets/sample.pdf'), 'application/pdf')]
        }
      end.to change(Conversation, :count).by(1)

      conversation = Conversation.last
      expect(response).to redirect_to("#{base}/requests/#{conversation.display_id}?created=1")
      expect(conversation).to have_attributes(inbox: api_inbox, contact: carla, status: 'new_ticket', subject: 'Não consigo emitir a VCN',
                                              additional_attributes: include('mail_subject' => 'Não consigo emitir a VCN'))
      created = conversation.conversation_events.find_by(event_type: 'create')
      expect(created).to have_attributes(via: 'customer', author: carla)
      expect(conversation.custom_attributes).to include(
        'zd_assunto' => 'Não consigo emitir a VCN', 'zd_formulario' => 'Atendimento', 'zd_canal' => 'Central de Ajuda',
        'zd_status' => 'Novo', 'zd_cnpj_o_cuit_argentina' => '12.345.678/0001-90'
      )
      message = conversation.messages.incoming.first
      expect([message.content.include?('abro o B2B.pay'), message.attachments.count]).to eq([true, 1])

      follow_redirect!
      expect(response.body).to include('foi enviada', 'Não consigo emitir a VCN', 'Aberto')
    end

    it 'recusa sem assunto, sem descrição ou com SVG' do
      sd_sign_in(portal, carla)
      expect do
        post "#{base}/requests", params: { subject: '', description: '' }
      end.not_to change(Conversation, :count)
      expect(response).to have_http_status(:unprocessable_entity)
      expect(response.body).to include('Informe o assunto.', 'Informe a descrição.')

      svg = Rack::Test::UploadedFile.new(StringIO.new('<svg onload="alert(1)"></svg>'), 'image/svg+xml', original_filename: 'x.svg')
      expect do
        post "#{base}/requests", params: { subject: 'a', description: 'b', attachments: [svg] }
      end.not_to change(Conversation, :count)
      expect(response).to have_http_status(:unprocessable_entity)
      expect(response.body).to include('não é aceito')
    end

    it 'avisa quando a inbox do formulário não está configurada' do
      portal.update!(config: portal.config.merge('customer_portal' => { 'enabled' => true }))
      sd_sign_in(portal, carla)
      post "#{base}/requests", params: { subject: 'a', description: 'b' }
      expect(response).to have_http_status(:unprocessable_entity)
      expect(response.body).to include('ainda não foi configurado')
    end

    it 'usa o formulário configurado no portal, com campo obrigatório' do
      portal.update!(config: portal.config.merge('customer_portal' => portal.customer_portal.merge(
        'request_forms' => [{ 'id' => 'ti', 'name' => 'Formulário TI', 'inbox_id' => api_inbox.id,
                              'fields' => [{ 'key' => 'sistema', 'label' => 'Sistema', 'type' => 'list', 'required' => true,
                                             'options' => %w[B2B.pay Booking], 'attribute_key' => 'zd_sistema' }] }]
      )))
      sd_sign_in(portal, carla)
      post "#{base}/requests", params: { form_id: 'ti', subject: 'a', description: 'b', fields: { sistema: 'Outro' } }
      expect(response).to have_http_status(:unprocessable_entity)
      expect(response.body).to include('Sistema')

      post "#{base}/requests", params: { form_id: 'ti', subject: 'a', description: 'b', fields: { sistema: 'Booking' } }
      expect(Conversation.last.custom_attributes).to include('zd_sistema' => 'Booking', 'zd_formulario' => 'Formulário TI')
    end
  end

  describe 'responder' do
    it 'adiciona comentário público do cliente com anexo' do
      sd_sign_in(portal, ana)
      post "#{base}/requests/#{ana_ticket.display_id}/comments",
           params: { content: 'Segue o print', attachments: [fixture_file_upload(Rails.root.join('spec/assets/sample.png'), 'image/png')] }
      expect(response).to redirect_to("#{base}/requests/#{ana_ticket.display_id}")
      message = ana_ticket.messages.reorder(:id).last
      expect(message).to have_attributes(content: 'Segue o print', message_type: 'incoming', sender: ana, private: false)
      expect(message.attachments.count).to eq(1)
    end

    it 'marca como resolvido' do
      sd_sign_in(portal, ana)
      post "#{base}/requests/#{ana_ticket.display_id}/comments", params: { content: 'Resolvido, obrigado', solve: '1' }
      expect(ana_ticket.reload).to be_resolved
      expect(ana_ticket.custom_attributes['zd_status']).to eq('Resolvido')
    end

    it 'resposta em ticket fechado abre um acompanhamento ligado a ele (o fechado não muda)' do
      sd_sign_in(portal, ana)
      get "#{base}/requests/#{ana_closed.display_id}"
      expect(response.body).to include('Sua resposta abrirá uma nova solicitação de acompanhamento', 'name="content"')

      expect do
        post "#{base}/requests/#{ana_closed.display_id}/comments", params: { content: 'O problema voltou' }
      end.to change(Conversation, :count).by(1)
      followup = Conversation.last
      expect(response).to redirect_to("#{base}/requests/#{followup.display_id}?created=1")
      expect(followup).to have_attributes(followup_source_id: ana_closed.id, contact_id: ana.id, status: 'new_ticket',
                                          inbox_id: api_inbox.id)
      expect(followup.messages.incoming.last).to have_attributes(content: 'O problema voltou', sender: ana)
      expect(followup.custom_attributes).to include('zd_canal' => 'Central de Ajuda', 'zd_status' => 'Novo')
      expect([ana_closed.reload.status, ana_closed.messages.where(content: 'O problema voltou').count]).to eq(['closed', 0])
    end

    it 'resposta em ticket fechado sem texto não cria acompanhamento' do
      sd_sign_in(portal, ana)
      expect do
        post "#{base}/requests/#{ana_closed.display_id}/comments", params: { content: ' ', solve: '1' }
      end.not_to change(Conversation, :count)
      expect(response).to have_http_status(:unprocessable_entity)
    end

    it 'resposta em ticket resolvido reabre o ticket' do
      ana_ticket.update_columns(status: Conversation.statuses[:resolved]) # rubocop:disable Rails/SkipsModelValidations
      sd_sign_in(portal, ana)
      post "#{base}/requests/#{ana_ticket.display_id}/comments", params: { content: 'Ainda não funcionou' }
      expect(response).to redirect_to("#{base}/requests/#{ana_ticket.display_id}")
      expect(ana_ticket.reload).to be_open
    end

    it 'resposta em ticket aguardando o cliente volta para Aberto' do
      sd_sign_in(portal, ana)
      post "#{base}/requests/#{ana_pending.display_id}/comments", params: { content: 'Segue o comprovante' }
      expect(ana_pending.reload).to be_open
    end

    it 'não dispara gatilhos nem e-mails (sem regras ativas)' do
      sd_sign_in(portal, carla)
      expect do
        post "#{base}/requests", params: { subject: 'Sem e-mail', description: 'teste' }
      end.not_to have_enqueued_job(ActionMailer::MailDeliveryJob)
      perform_enqueued_jobs
      expect(ActionMailer::Base.deliveries).to be_empty
    end

    it 'exige texto, anexo ou resolver' do
      sd_sign_in(portal, ana)
      post "#{base}/requests/#{ana_ticket.display_id}/comments", params: { content: '  ' }
      expect(response).to have_http_status(:unprocessable_entity)
      expect(response.body).to include('Escreva uma resposta')
    end
  end
end
