require 'rails_helper'

RSpec.describe 'Zendesk compat: usuários, grupos, organizações e busca', type: :request do
  include_context 'with zendesk compat data'

  describe 'GET /api/v2/users' do
    it 'show_many resolve agentes, contatos e ids desconhecidos' do
      ticket
      get "/api/v2/users/show_many.json?ids=#{ai_agent_zid},24033324330395,31255458137883,999", headers: headers
      users = json['users'].index_by { |user| user['id'] }
      expect(users.keys).to contain_exactly(ai_agent_zid, 24_033_324_330_395, 31_255_458_137_883)
      expect(users[ai_agent_zid]).to include('role' => 'admin', 'email' => 'agenteia.suporte@example.com', 'name' => 'Cema')
      expect(users[24_033_324_330_395]).to include('role' => 'end-user', 'phone' => '+5511999990000', 'organization_id' => 21_300_000_000_001)
      expect(users[24_033_324_330_395]['user_fields']).to include('cnpj' => '00.000.000/0001-00')
    end

    it 'show devolve 404 para id desconhecido e usa USER_BASE para agente sem id de origem' do
      plain_agent = create(:user, account: account, role: :agent)
      get "/api/v2/users/#{ZendeskCompat::Ids::USER_BASE + plain_agent.id}.json", headers: headers
      expect(json['user']).to include('id' => ZendeskCompat::Ids::USER_BASE + plain_agent.id, 'role' => 'agent')

      get '/api/v2/users/123456789.json', headers: headers
      expect(response).to have_http_status(:not_found)
    end

    it 'contato novo (sem zd) usa o próprio id, como o {{ticket.requester.id}} dos webhooks' do
      contact = create(:contact, account: account, email: 'novo@example.com')
      get "/api/v2/users/#{contact.id}.json", headers: headers
      expect(json['user']).to include('id' => contact.id, 'email' => 'novo@example.com', 'role' => 'end-user')
    end

    it 'search por e-mail e por query' do
      requester
      get '/api/v2/users/search.json?query=hotel-exemplo', headers: headers
      expect(json['users'].pluck('id')).to include(24_033_324_330_395)
      get '/api/v2/users/search.json?email=agenteia.suporte@example.com', headers: headers
      expect(json['users'].pluck('id')).to eq([ai_agent_zid])
    end
  end

  describe 'GET /api/v2/groups' do
    before { support_team.add_members([human_agent.id, cema.id]) }

    it 'memberships e users pelo id do grupo no Zendesk' do
      get "/api/v2/groups/#{support_group_zid}/memberships.json?per_page=100", headers: headers
      expect(json['group_memberships'].pluck('user_id')).to contain_exactly(21_000_000_000_001, ai_agent_zid)
      expect(json['group_memberships'].first['group_id']).to eq(support_group_zid)
      expect(json['next_page']).to be_nil

      get "/api/v2/groups/#{support_group_zid}/users", headers: headers
      expect(json['users'].pluck('name')).to contain_exactly('Agente Humano', 'Cema')
    end

    it 'index e show' do
      get '/api/v2/groups.json', headers: headers
      expect(json['groups']).to include(include('id' => support_group_zid, 'name' => 'suporte'))
      get '/api/v2/groups/0.json', headers: headers
      expect(response).to have_http_status(:not_found)
    end
  end

  describe 'GET /api/v2/organizations' do
    it 'show pelo zd_org_id' do
      company
      get '/api/v2/organizations/21300000000001.json', headers: headers
      expect(json['organization']).to include('id' => 21_300_000_000_001, 'name' => 'Hotel Exemplo')
    end
  end

  describe 'GET /api/v2/search' do
    before do
      ticket
      chat_ticket.update!(status: status_for(:solved), custom_attributes: chat_ticket.custom_attributes.merge('zd_status' => 'Resolvido'))
      other = create_ticket(430_001, inbox: email_inbox, assignee: human_agent, custom_attributes: { 'zd_status' => 'Pendente' })
      other.update!(status: status_for(:pending))
    end

    it 'busca da Monitor Intervenção Humana: assignee + status<solved + updated>' do
      query = "type:ticket assignee:#{ai_agent_zid} status<solved updated>#{1.day.ago.to_date.iso8601}"
      get "/api/v2/search.json?#{{ query: query, per_page: 100 }.to_query}", headers: headers
      expect(json['results'].pluck('id')).to eq([426_563])
      expect(json['results'].first).to include('result_type' => 'ticket', 'status' => 'open')
      expect(json).to include('count' => 1, 'next_page' => nil)
    end

    it 'status, grupo, tags, datas relativas, campo personalizado e count' do
      get "/api/v2/search.json?#{{ query: 'status:pending' }.to_query}", headers: headers
      expect(json['results'].pluck('id')).to eq([430_001])

      get "/api/v2/search.json?#{{ query: "group:#{support_group_zid} tags:cancelamento -tags:vip status>=solved" }.to_query}", headers: headers
      expect(json['results'].pluck('id')).to eq([427_406])

      get "/api/v2/search.json?#{{ query: 'created>2hours assignee:none' }.to_query}", headers: headers
      expect(json['results']).to eq([])

      get "/api/v2/search.json?#{{ query: "custom_field_#{tabulacao_field_id}:suporte_checkout_-_estorno" }.to_query}", headers: headers
      expect(json['results'].pluck('id')).to eq([426_563])

      get "/api/v2/search/count.json?#{{ query: 'type:ticket status<solved' }.to_query}", headers: headers
      expect(json['count']).to eq(2)
    end

    it 'recusa termo desconhecido em vez de devolver resultado errado' do
      get "/api/v2/search.json?#{{ query: 'satisfaction:good' }.to_query}", headers: headers
      expect(response).to have_http_status(:bad_request)
      expect(json['error']).to eq('UnsupportedByServiceDesk')
    end
  end
end
