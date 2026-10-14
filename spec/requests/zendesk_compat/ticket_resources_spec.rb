# rubocop:disable RSpec/MultipleExpectations
require 'rails_helper'

RSpec.describe 'Zendesk compat: recursos do ticket', type: :request do
  include_context 'with zendesk compat data'

  describe 'GET /api/v2/tickets/:id/comments' do
    it 'devolve comentários públicos e internos com autor, anexos e usuários (include=users)' do
      ticket_with_history
      get "/api/v2/tickets/#{ticket.display_id}/comments.json?include=users", headers: headers

      comments = json['comments']
      expect(comments.size).to eq(3)
      expect(comments.pluck('author_id')).to eq([24_033_324_330_395, 21_000_000_000_001, ai_agent_zid])
      expect(comments.pluck('public')).to eq([true, false, true])
      expect(comments.last['attachments'].first).to include('file_name' => 'sample.pdf', 'content_type' => 'application/pdf')
      expect(comments.last['attachments'].first['content_url']).to include('/rails/active_storage/blobs/')
      expect(comments.first).to include('plain_body' => 'Bom dia, preciso cancelar a reserva 21429607.', 'type' => 'Comment')
      expect(json['users'].to_h { |u| [u['id'], u['role']] }).to include(ai_agent_zid => 'admin', 21_000_000_000_001 => 'agent',
                                                                         24_033_324_330_395 => 'end-user')
      expect(json).to include('next_page' => nil, 'previous_page' => nil, 'count' => 3)
    end

    it 'ordena por sort_order=desc e pagina com per_page' do
      ticket_with_history
      get "/api/v2/tickets/#{ticket.display_id}/comments.json?sort_order=desc&per_page=2", headers: headers
      expect(json['comments'].first['author_id']).to eq(ai_agent_zid)
      expect(json['next_page']).to include('page=2').and include('per_page=2').and include('sort_order=desc')

      get json['next_page'].sub('http://www.example.com', ''), headers: headers
      expect(json['comments'].size).to eq(1)
      expect(json['previous_page']).to include('page=1')
    end

    it 'não lista mensagens de atividade' do
      ticket.messages.create!(account: account, inbox: ticket.inbox, message_type: :activity, content: 'Atribuído a Cema')
      get "/api/v2/tickets/#{ticket.display_id}/comments.json", headers: headers
      expect(json['comments']).to be_empty
    end
  end

  describe 'GET /api/v2/tickets/:id/audits' do
    it 'monta o 1º audit com Create + 1º comentário, um audit por comentário e um por alteração registrada' do
      ticket_with_history
      put "/api/v2/tickets/#{ticket.display_id}.json", params: { ticket: { assignee_id: 21_000_000_000_001, status: 'pending' } }.to_json,
                                                       headers: json_headers
      get "/api/v2/tickets/#{ticket.display_id}/audits.json?page[size]=100", headers: headers

      audits = json['audits']
      expect(audits.first['events'].pluck('type')).to include('Create', 'Comment')
      create_assignee = audits.first['events'].find { |e| e['type'] == 'Create' && e['field_name'] == 'assignee_id' }
      expect(create_assignee['value']).to eq(ai_agent_zid.to_s)
      change = audits.last
      expect(change).to include('author_id' => ai_agent_zid, 'ticket_id' => ticket.display_id)
      expect(change['via']['channel']).to eq('api')
      expect(change['events']).to include(include('field_name' => 'assignee_id', 'value' => '21000000000001', 'previous_value' => ai_agent_zid.to_s),
                                          include('field_name' => 'status', 'value' => 'pending', 'previous_value' => 'open'))
      expect(json['meta']).to include('has_more' => false)
      expect(json['links']).to include('next' => nil)
    end

    it 'pagina por cursor (page[size] / page[after]) como o Zendesk' do
      ticket_with_history
      get "/api/v2/tickets/#{ticket.display_id}/audits.json?page[size]=100", headers: headers
      all_ids = json['audits'].pluck('id')
      expect(all_ids.size).to be >= 3

      ids = []
      url = "/api/v2/tickets/#{ticket.display_id}/audits.json?page[size]=2"
      while url
        get url, headers: headers
        expect(json['audits'].size).to be <= 2
        ids += json['audits'].pluck('id')
        url = json['meta']['has_more'] ? json['links']['next'].sub('http://www.example.com', '') : nil
      end
      expect(ids).to eq(all_ids)
    end

    it 'registra alterações feitas fora da API (painel, regras) com o autor' do
      Current.user = human_agent
      ticket.update!(team: nil, priority: :urgent)
      Current.reset
      audit = Servicedesk::TicketAudit.last
      expect(audit).to have_attributes(author: human_agent, via: 'web')
      expect(audit.events).to include(include('field_name' => 'group_id', 'previous_value' => support_group_zid.to_s, 'value' => nil),
                                      include('field_name' => 'priority', 'value' => 'urgent'))
    end
  end

  describe 'GET /api/v2/tickets/:id/email_ccs' do
    it 'devolve os CCs do ticket como usuários' do
      get "/api/v2/tickets/#{ticket.display_id}/email_ccs.json", headers: headers
      expect(json['users']).to contain_exactly(include('id' => 31_255_458_137_883, 'email' => 'agencia@agencia-exemplo.com.br', 'role' => 'end-user'))
    end
  end

  describe 'GET /api/v2/tickets/:id/conversation_log' do
    it 'devolve as mensagens do chat como Messaging::ConversationMessage com o tipo do autor' do
      add_message(chat_ticket, type: :incoming, content: 'Oi, quero cancelar', sender: requester, created_at: 5.minutes.ago)
      add_message(chat_ticket, type: :outgoing, content: 'Olá! Qual o localizador?', sender: cema, created_at: 4.minutes.ago)
      add_message(chat_ticket, type: :outgoing, content: 'nota', sender: human_agent, private: true, created_at: 3.minutes.ago)
      get "/api/v2/tickets/#{chat_ticket.display_id}/conversation_log", headers: headers

      events = json['events']
      expect(events.pluck('type')).to eq(%w[Messaging::ConversationMessage Messaging::ConversationMessage Comment])
      expect(events.first['author']).to include('type' => 'end-user', 'zen:sunco:user_id' => "sd-contact-#{requester.id}")
      expect(events.first['content']).to include('type' => 'text', 'text' => 'Oi, quero cancelar')
      expect(events.second['author']).to include('type' => 'agent', 'zen:support:user_id' => ai_agent_zid)
      expect(events.third['metadata']).to include('public' => false)
    end
  end

  describe '/api/v2/tickets/:id/tags' do
    it 'PUT acrescenta, POST substitui, DELETE remove e GET lista (semântica do Zendesk)' do
      put "/api/v2/tickets/#{ticket.display_id}/tags.json", params: { tags: ['cancelamento_pos_follow_up_conferido'] }.to_json, headers: json_headers
      expect(json['tags']).to eq(%w[atendimento_ia cancelamento cancelamento_pos_follow_up_conferido])

      post "/api/v2/tickets/#{ticket.display_id}/tags.json", params: { tags: %w[no_ai erro_consulta_checkout] }.to_json, headers: json_headers
      expect(json['tags']).to eq(%w[erro_consulta_checkout no_ai])

      delete "/api/v2/tickets/#{ticket.display_id}/tags.json", params: { tags: ['no_ai'] }.to_json, headers: json_headers
      expect(json['tags']).to eq(['erro_consulta_checkout'])

      get "/api/v2/tickets/#{ticket.display_id}/tags.json", headers: headers
      expect(json['tags']).to eq(['erro_consulta_checkout'])
      expect(ticket.reload.label_list).to eq(['erro_consulta_checkout'])
    end

    it 'normaliza tags como a importação' do
      put "/api/v2/tickets/#{ticket.display_id}/tags.json", params: { tags: ['Excluído/Spam', 'x'] }.to_json, headers: json_headers
      expect(json['tags']).to include('excluído_spam', 'tag_x')
    end
  end
end
# rubocop:enable RSpec/MultipleExpectations
