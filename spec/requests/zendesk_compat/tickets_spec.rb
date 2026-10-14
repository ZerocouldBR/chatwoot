# rubocop:disable RSpec/MultipleExpectations
require 'rails_helper'

RSpec.describe 'Zendesk compat: /api/v2/tickets', type: :request do
  include_context 'with zendesk compat data'

  describe 'autenticação' do
    it 'aceita Basic "email/token:token" do usuário administrador' do
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: headers
      expect(response).to have_http_status(:ok)
    end

    it 'aceita Bearer com o token de acesso' do
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: { 'Authorization' => "Bearer #{cema.access_token.token}" }
      expect(response).to have_http_status(:ok)
    end

    it 'responde 401 no formato do Zendesk sem credencial, com token errado ou com e-mail de outro usuário' do
      get "/api/v2/tickets/#{ticket.display_id}.json"
      expect(response).to have_http_status(:unauthorized)
      expect(json).to eq('error' => "Couldn't authenticate you")

      get "/api/v2/tickets/#{ticket.display_id}.json", headers: zendesk_basic_headers(cema, token: 'invalido')
      expect(response).to have_http_status(:unauthorized)

      wrong_email = { 'Authorization' => ActionController::HttpAuthentication::Basic.encode_credentials("#{human_agent.email}/token",
                                                                                                        cema.access_token.token) }
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: wrong_email
      expect(response).to have_http_status(:unauthorized)
    end

    it 'responde 403 para quem não é administrador da conta' do
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: zendesk_basic_headers(human_agent)
      expect(response).to have_http_status(:forbidden)
      expect(json['error']).to eq('Forbidden')
    end

    it 'fica fora do ar (404) sem ZENDESK_COMPAT_ENABLED' do
      ticket
      ENV.delete('ZENDESK_COMPAT_ENABLED')
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: headers
      expect(response).to have_http_status(:not_found)
    end
  end

  describe 'GET /api/v2/tickets/:id' do
    it 'devolve o ticket importado no formato do Zendesk' do
      ticket_with_history
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: headers

      data = json['ticket']
      expect(data['custom_status_id']).to eq(20_487_400_901_659) if ZendeskCompat::TicketModel.labels?
      expect(data).to include('id' => 426_563, 'status' => 'open',
                              'assignee_id' => ai_agent_zid, 'group_id' => support_group_zid, 'requester_id' => 24_033_324_330_395,
                              'organization_id' => 21_300_000_000_001, 'subject' => 'Reserva 21429607 - cancelamento',
                              'type' => 'task', 'tags' => %w[atendimento_ia cancelamento], 'email_cc_ids' => [31_255_458_137_883],
                              'description' => 'Bom dia, preciso cancelar a reserva 21429607.')
      expect(data['via']).to include('channel' => 'email')
      expect(data.dig('via', 'source', 'to', 'address')).to eq('atendimentob2b@b2breservas.com.br')
      expect(data['custom_fields']).to include({ 'id' => tabulacao_field_id, 'value' => 'suporte_checkout_-_estorno' })
      expect(data['fields']).to eq(data['custom_fields'])
    end

    it 'aceita o prefixo /<subdominio>.zendesk.com e mantém o prefixo nas URLs devolvidas' do
      get "/b2b-reservas.zendesk.com/api/v2/tickets/#{ticket.display_id}.json", headers: headers
      expect(response).to have_http_status(:ok)
      expect(json.dig('ticket', 'url')).to end_with("/b2b-reservas.zendesk.com/api/v2/tickets/#{ticket.display_id}.json")
    end

    it 'faz o sideload include=users' do
      get "/api/v2/tickets/#{ticket.display_id}.json?include=users", headers: headers
      roles = json['users'].to_h { |user| [user['id'], user['role']] }
      expect(roles).to include(ai_agent_zid => 'admin', 24_033_324_330_395 => 'end-user', 31_255_458_137_883 => 'end-user')
    end

    it 'deriva o status da categoria do rótulo e trata o rótulo que ficou para trás', :legacy_ticket_model do
      ticket.update!(custom_attributes: ticket.custom_attributes.merge('zd_status' => 'Pendente'), status: :snoozed)
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: headers
      expect(json['ticket']).to include('status' => 'pending', 'custom_status_id' => 20_487_412_004_251)

      ticket.update!(status: :open) # o cliente respondeu e o Chatwoot reabriu; o rótulo ainda diz Pendente
      get "/api/v2/tickets/#{ticket.display_id}.json", headers: headers
      expect(json['ticket']).to include('status' => 'open', 'custom_status_id' => 20_487_400_901_659)
    end

    it 'responde 404 no formato do Zendesk' do
      get '/api/v2/tickets/999999.json', headers: headers
      expect(response).to have_http_status(:not_found)
      expect(json).to eq('error' => 'RecordNotFound', 'description' => 'Not found')
    end

    it 'não enxerga ticket de outra conta' do
      other = create(:conversation, account: create(:account))
      get "/api/v2/tickets/#{other.display_id}.json", headers: headers
      expect(response).to have_http_status(:not_found)
    end
  end

  describe 'GET /api/v2/tickets/show_many' do
    it 'devolve os tickets pedidos' do
      ids = [ticket.display_id, chat_ticket.display_id]
      get "/api/v2/tickets/show_many.json?ids=#{ids.join(',')}", headers: headers
      expect(json['tickets'].pluck('id')).to match_array(ids)
    end
  end

  describe 'PUT /api/v2/tickets/:id' do
    def put_ticket(payload)
      put "/api/v2/tickets/#{ticket.display_id}.json", params: { ticket: payload }.to_json, headers: json_headers
    end

    it 'reatribui pelo id do Zendesk do agente (nó "atualiza_assignee" / "reatribui_cema")' do
      put_ticket(assignee_id: 21_000_000_000_001)
      expect(response).to have_http_status(:ok)
      expect(json.dig('ticket', 'assignee_id')).to eq(21_000_000_000_001)
      expect(ticket.reload.assignee).to eq(human_agent)
      expect(json.dig('audit', 'events')).to include(include('type' => 'Change', 'field_name' => 'assignee_id',
                                                             'value' => '21000000000001', 'previous_value' => ai_agent_zid.to_s))
    end

    it 'aplica status, tabulação e nota interna (payload do "Cataloga Tickets Zendesk")', :legacy_ticket_model do
      put_ticket(status: 'solved', custom_fields: [{ id: tabulacao_field_id, value: 'cancelamento_interno' }],
                 comment: { body: 'Tabulação automática: cancelamento interno.', public: false })
      ticket.reload
      expect(ticket).to be_resolved
      expect(ticket.custom_attributes).to include('zd_status' => 'Resolvido', 'zd_tabulacao' => 'Cancelamento Interno')
      note = ticket.messages.last
      expect(note).to have_attributes(private: true, content: 'Tabulação automática: cancelamento interno.', sender: cema)
      expect(json['ticket']).to include('status' => 'solved', 'custom_status_id' => 20_487_384_870_939)
    end

    it 'responde em público com html, anexo e CCs (payload do "Tratamento Envio")', :legacy_ticket_model do
      blob = ZendeskCompat::Uploads.create(io: StringIO.new('%PDF-1.4'), filename: 'comprovante.pdf', content_type: 'application/pdf')
      put_ticket(status: 'pending', email_ccs: [{ user_email: 'Financeiro@Agencia-Exemplo.com.br', action: 'put' }],
                 comment: { html_body: '<p>Olá!<br>Segue o <b>comprovante</b>.</p>', public: true, uploads: [ZendeskCompat::Uploads.token(blob)] })
      ticket.reload
      message = ticket.messages.last
      expect(message).to have_attributes(private: false, message_type: 'outgoing')
      expect(message.content).to include('**comprovante**')
      expect(message.attachments.first.file.blob).to eq(blob)
      expect(message.content_attributes['cc_emails']).to match_array(%w[agencia@agencia-exemplo.com.br financeiro@agencia-exemplo.com.br])
      expect(ticket.custom_attributes['zd_status']).to eq('Pendente')
      expect(ticket).to be_snoozed
    end

    it 'remove CC com action delete (nó "atualiza_ccs")', :legacy_ticket_model do
      put_ticket(email_ccs: [{ user_email: 'agencia@agencia-exemplo.com.br', action: 'delete' }])
      expect(ticket.reload.custom_attributes).not_to have_key('zd_cc')
      expect(json.dig('ticket', 'email_cc_ids')).to eq([])
    end

    it 'aceita custom_status_id, group_id, priority, type, tags e additional/remove_tags', :legacy_ticket_model do
      put_ticket(custom_status_id: 21_790_243_451_291, group_id: support_group_zid, priority: 'high', type: 'incident',
                 additional_tags: ['vip'], remove_tags: ['atendimento_ia'])
      ticket.reload
      expect(ticket.custom_attributes).to include('zd_status' => 'Desenvolvimento', 'zd_tipo' => 'Incidente')
      expect(ticket).to be_snoozed
      expect(ticket.priority).to eq('high')
      expect(ticket.label_list).to match_array(%w[cancelamento vip])
      expect(json['ticket']).to include('status' => 'hold', 'priority' => 'high', 'type' => 'incident')
    end

    it 'grava o autor informado em comment.author_id' do
      put_ticket(comment: { body: 'Nota do agente', public: false, author_id: 21_000_000_000_001 })
      expect(ticket.messages.last.sender).to eq(human_agent)
    end

    it 'responde 422 no formato do Zendesk para responsável, status ou upload inválidos' do
      put_ticket(assignee_id: 123)
      expect(response).to have_http_status(:unprocessable_entity)
      expect(json).to include('error' => 'RecordInvalid', 'description' => 'Record validation errors')
      expect(json.dig('details', 'assignee', 0, 'description')).to be_present

      put_ticket(status: 'inexistente')
      expect(response).to have_http_status(:unprocessable_entity)

      put_ticket(comment: { body: 'x', uploads: ['token-invalido'] })
      expect(response).to have_http_status(:unprocessable_entity)
      expect(ticket.reload.messages.where(content: 'x')).to be_empty
    end

    it 'respeita safe_update com updated_stamp antigo (409)' do
      put_ticket(status: 'solved', safe_update: true, updated_stamp: 1.day.ago.iso8601)
      expect(response).to have_http_status(:conflict)
      expect(json['error']).to eq('UpdateConflict')
      expect(ticket.reload).to be_open
    end

    it 'exige o objeto ticket (400)' do
      put "/api/v2/tickets/#{ticket.display_id}.json", params: { foo: 1 }.to_json, headers: json_headers
      expect(response).to have_http_status(:bad_request)
    end
  end

  describe 'POST /api/v2/tickets' do
    it 'cria o ticket com solicitante novo, caixa do destinatário, CCs e comentário (payload do "Envolve Agência")', :legacy_ticket_model do
      email_inbox
      support_team.add_members([cema.id]) # como no Zendesk, o responsável precisa ser do grupo (senão o ServiceDesk tira o responsável)
      payload = { ticket: { requester: { email: 'hotel.novo@example.com', name: 'Hotel Novo' },
                            subject: 'Reserva 21100070 — Pendência de cobrança',
                            assignee_id: ai_agent_zid, group_id: support_group_zid, recipient: 'atendimentob2b@example.com',
                            tags: ['ajuda_para_cobrança'],
                            comment: { html_body: 'Olá,<br>segue a pendência.', public: true, author_id: ai_agent_zid },
                            email_ccs: [{ user_email: 'agencia@agencia-exemplo.com.br', action: 'put' }], external_id: 'parent:426563' } }
      expect do
        post '/api/v2/tickets.json', params: payload.to_json, headers: json_headers
      end.to change(account.conversations, :count).by(1), -> { response.body }

      expect(response).to have_http_status(:created)
      conversation = account.conversations.find_by(display_id: json.dig('ticket', 'id'))
      expect(conversation.inbox).to eq(email_inbox)
      expect(conversation.contact.email).to eq('hotel.novo@example.com')
      expect(conversation.assignee).to eq(cema)
      expect(conversation.custom_attributes).to include('zd_cc' => 'agencia@agencia-exemplo.com.br', 'zd_id_externo' => 'parent:426563')
      expect(conversation.messages.last).to have_attributes(sender: cema, private: false)
      expect(json['ticket']).to include('subject' => 'Reserva 21100070 — Pendência de cobrança', 'status' => 'open', 'group_id' => support_group_zid)
      expect(response.headers['Location']).to end_with("/api/v2/tickets/#{conversation.display_id}.json")
    end

    it 'responde 422 sem solicitante' do
      email_inbox
      post '/api/v2/tickets.json', params: { ticket: { subject: 'x', comment: { body: 'y' } } }.to_json, headers: json_headers
      expect(response).to have_http_status(:unprocessable_entity)
    end
  end
end
# rubocop:enable RSpec/MultipleExpectations
