require 'rails_helper'

RSpec.describe 'Zendesk compat: campos, status, uploads, notificações e disponibilidade', type: :request do
  include_context 'with zendesk compat data'

  describe 'GET /api/v2/ticket_fields (teste de credencial do n8n)' do
    it 'lista os campos com as opções (tag) e o atributo do ServiceDesk' do
      get '/api/v2/ticket_fields.json', headers: headers
      expect(response).to have_http_status(:ok)
      tabulacao = json['ticket_fields'].find { |field| field['id'] == tabulacao_field_id }
      expect(tabulacao).to include('type' => 'tagger', 'title' => 'Tabulação', 'servicedesk_attribute_key' => 'zd_tabulacao')
      expect(tabulacao['custom_field_options']).to include(include('name' => 'Checkout - Estorno', 'value' => 'suporte_checkout_-_estorno'))
      expect(json['count']).to eq(ZendeskCompat::Config.ticket_fields.size)
    end
  end

  describe 'GET /api/v2/custom_statuses' do
    it 'lista os status personalizados com a categoria', :custom_statuses do
      get '/api/v2/custom_statuses.json', headers: headers
      pendente = json['custom_statuses'].find { |status| status['agent_label'] == 'Pendente' }
      expect(pendente).to include('id' => 20_487_412_004_251, 'status_category' => 'pending', 'end_user_label' => 'Aguardando resposta',
                                  'default' => true)
    end
  end

  describe 'POST /api/v2/uploads' do
    it 'recebe o arquivo no corpo (binaryData do n8n) e devolve o token' do
      body = File.binread(Rails.root.join('spec/assets/sample.pdf'))
      post '/api/v2/uploads.json?filename=comprovante.pdf', params: body, headers: headers.merge('Content-Type' => 'application/pdf')

      expect(response).to have_http_status(:created)
      upload = json['upload']
      expect(upload['token']).to be_present
      expect(upload['attachment']).to include('file_name' => 'comprovante.pdf', 'content_type' => 'application/pdf', 'size' => body.bytesize)
      expect(ZendeskCompat::Uploads.find(upload['token']).download).to eq(body)
    end

    it 'detecta o tipo quando o n8n manda application/octet-stream' do
      png = File.binread(Rails.root.join('spec/assets/sample.png'))
      post '/api/v2/uploads?filename=foto.png', params: png, headers: headers.merge('Content-Type' => 'application/octet-stream')
      expect(json.dig('upload', 'attachment', 'content_type')).to eq('image/png')
    end

    it 'recusa corpo vazio (400)' do
      post '/api/v2/uploads.json?filename=x.pdf', params: '', headers: headers.merge('Content-Type' => 'application/pdf')
      expect(response).to have_http_status(:bad_request)
    end
  end

  describe 'GET /api/v2/email_notifications' do
    it 'lista as entregas dos comentários públicos com destinatários e status (CC Agent)' do
      ticket_with_history
      failed = add_message(ticket, type: :outgoing, content: 'Resposta', sender: cema)
      failed.update!(status: :failed, content_attributes: { 'cc_emails' => ['agencia@agencia-exemplo.com.br'],
                                                            'external_error' => '550 5.1.1 recipient address rejected: user unknown' })
      get "/api/v2/email_notifications?#{{ filter: { ticket_id: ticket.display_id }, per_page: 100 }.to_query}", headers: headers

      notifications = json['email_notifications']
      expect(notifications.size).to eq(2)
      expect(notifications.first['recipients'].first).to include('user_id' => 24_033_324_330_395, 'email_address' => 'reservas@hotel-exemplo.com.br')
      expect(notifications.first['recipients'].first['delivery_status']).to include('name' => 'delivered')
      bounced = notifications.last['recipients'].find { |r| r['email_address'] == 'agencia@agencia-exemplo.com.br' }
      expect(bounced).to include('user_id' => 31_255_458_137_883)
      expect(bounced['delivery_status']).to include('id' => 37, 'name' => 'invalid_recipient')
    end

    it 'exige filter[ticket_id]' do
      get '/api/v2/email_notifications', headers: headers
      expect(response).to have_http_status(:bad_request)
    end
  end

  describe 'GET /api/v2/agent_availabilities' do
    it 'devolve agentes do grupo com status e carga por canal (formato JSON:API)' do
      support_team.add_members([human_agent.id, cema.id])
      ticket
      account.account_users.find_by(user: human_agent).update!(availability: :online)
      allow(OnlineStatusTracker).to receive(:get_presence).and_return(true)

      get "/api/v2/agent_availabilities?#{{ filter: { group_id: support_group_zid } }.to_query}", headers: headers

      agents = json['data'].index_by { |item| item.dig('attributes', 'agent_id') }
      expect(agents.keys).to contain_exactly(21_000_000_000_001, ai_agent_zid)
      expect(agents[21_000_000_000_001].dig('attributes', 'agent_status', 'name')).to eq('Online')
      support = json['included'].find { |item| item['id'] == "agent_availabilities|#{ai_agent_zid}|channels|support" }
      expect(support['attributes']).to include('name' => 'support', 'work_item_count' => 1, 'max_capacity' => 20)
    end
  end
end
