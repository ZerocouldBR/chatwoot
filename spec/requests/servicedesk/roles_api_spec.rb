# frozen_string_literal: true

require 'rails_helper'

# ServiceDesk M13: enforcement dos papéis pela API HTTP real (o mesmo caminho do painel).
RSpec.describe 'ServiceDesk M13 - papéis na API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { member('administrador', base: :administrator) }
  let(:agente) { member('agente', teams: [suporte]) }
  let(:light) { member('agente_light', teams: [suporte]) }
  let(:colaborador) { member('colaborador', teams: [suporte]) }
  let(:ticket) { create(:conversation, account: account, inbox: inbox, team: suporte) }
  let(:ticket_ti) { create(:conversation, account: account, inbox: inbox, team: ti) }
  let(:inbox) { create(:inbox, account: account) }
  let(:suporte) { create(:team, account: account, name: 'Suporte') }
  let(:ti) { create(:team, account: account, name: 'TI - N2') }

  def member(role_key, base: :agent, teams: [])
    user = create(:user, account: account, role: base)
    account.account_users.find_by!(user: user).update!(sd_role: account.sd_roles.find_by!(key: role_key))
    create(:inbox_member, inbox: inbox, user: user)
    teams.each { |t| create(:team_member, team: t, user: user) }
    user
  end

  def messages_url(conversation)
    api_v1_account_conversation_messages_url(account_id: account.id, conversation_id: conversation.display_id)
  end

  describe 'resposta pública x nota interna' do
    it 'agente light não envia resposta pública (403) e grava nota interna' do
      post messages_url(ticket), params: { content: 'resposta ao cliente', private: false }, headers: light.create_new_auth_token, as: :json
      expect(response).to have_http_status(:forbidden)
      expect(response.parsed_body['error']).to include('nota interna')

      post messages_url(ticket), params: { content: 'nota do light', private: true }, headers: light.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      expect(ticket.messages.pluck(:content, :private)).to eq([['nota do light', true]])
    end

    it 'agente e administrador enviam resposta pública' do
      post messages_url(ticket), params: { content: 'resposta', private: false }, headers: agente.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      post messages_url(ticket), params: { content: 'resposta admin' }, headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      expect(ticket.messages.where(private: false).count).to eq(2)
    end

    it 'agente light não abre conversa nova com o cliente nem envia transcrição' do
      post api_v1_account_conversations_url(account_id: account.id), params: { inbox_id: inbox.id }, headers: light.create_new_auth_token, as: :json
      expect(response).to have_http_status(:forbidden)
    end

    it 'agente (sem ticket.redact) não apaga mensagem; administrador apaga' do
      message = create(:message, conversation: ticket, account: account, inbox: inbox, content: 'texto')
      url = api_v1_account_conversation_message_url(account_id: account.id, conversation_id: ticket.display_id, id: message.id)
      delete url, headers: agente.create_new_auth_token, as: :json
      expect(response).to have_http_status(:forbidden)
      delete url, headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
    end
  end

  describe 'editar ticket' do
    it 'agente light não muda status, prioridade, responsável nem etiquetas' do
      headers = light.create_new_auth_token
      post toggle_status_api_v1_account_conversation_url(account_id: account.id, id: ticket.display_id), params: { status: 'resolved' },
                                                                                                         headers: headers, as: :json
      expect(response).to have_http_status(:forbidden)
      post api_v1_account_conversation_assignments_url(account_id: account.id, conversation_id: ticket.display_id),
           params: { assignee_id: light.id }, headers: headers, as: :json
      expect(response).to have_http_status(:forbidden)
      post api_v1_account_conversation_labels_url(account_id: account.id, conversation_id: ticket.display_id),
           params: { labels: ['vip'] }, headers: headers, as: :json
      expect(response).to have_http_status(:forbidden)
      expect(ticket.reload.status).to eq('open')
    end

    it 'agente muda o status' do
      url = toggle_status_api_v1_account_conversation_url(account_id: account.id, id: ticket.display_id)
      post url, params: { status: 'resolved' }, headers: agente.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      expect(ticket.reload.status).to eq('resolved')
    end

    it 'ninguém atribui ticket a agente light (não pode ser responsável), nem o administrador' do
      post api_v1_account_conversation_assignments_url(account_id: account.id, conversation_id: ticket.display_id),
           params: { assignee_id: light.id }, headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:forbidden)
      post api_v1_account_conversation_assignments_url(account_id: account.id, conversation_id: ticket.display_id),
           params: { assignee_id: agente.id }, headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      expect(ticket.reload.assignee).to eq(agente)
    end

    it 'agentes atribuíveis da inbox não incluem light nem colaborador' do
      [agente, light, colaborador, admin]
      get api_v1_account_assignable_agents_url(account_id: account.id), params: { inbox_ids: [inbox.id] }, headers: admin.create_new_auth_token
      ids = response.parsed_body['payload'].pluck('id')
      expect(ids).to include(agente.id, admin.id)
      expect(ids).not_to include(light.id, colaborador.id)
    end

    it 'excluir ticket: agente (Zendesk permite) sim; light não' do
      other = create(:conversation, account: account, inbox: inbox, team: suporte)
      delete api_v1_account_conversation_url(account_id: account.id, id: other.display_id), headers: light.create_new_auth_token, as: :json
      expect(response).to have_http_status(:unauthorized)
      delete api_v1_account_conversation_url(account_id: account.id, id: other.display_id), headers: agente.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
    end
  end

  describe 'visibilidade por grupo' do
    it 'colaborador não abre nem lista ticket de outro grupo; admin vê tudo' do
      [ticket, ticket_ti]
      get api_v1_account_conversation_url(account_id: account.id, id: ticket_ti.display_id), headers: colaborador.create_new_auth_token, as: :json
      expect(response).to have_http_status(:unauthorized)

      get api_v1_account_conversations_url(account_id: account.id), params: { status: 'all' }, headers: colaborador.create_new_auth_token
      expect(response.parsed_body['data']['payload'].pluck('id')).to eq([ticket.display_id])

      get api_v1_account_conversations_url(account_id: account.id), params: { status: 'all' }, headers: admin.create_new_auth_token
      expect(response.parsed_body['data']['payload'].pluck('id')).to contain_exactly(ticket.display_id, ticket_ti.display_id)
    end
  end

  describe 'contatos, relatórios e macros' do
    it 'colaborador não lista usuários finais; light lista mas não edita' do
      contact = create(:contact, account: account)
      get api_v1_account_contacts_url(account_id: account.id), headers: colaborador.create_new_auth_token
      expect(response).to have_http_status(:unauthorized)
      get api_v1_account_contacts_url(account_id: account.id), headers: light.create_new_auth_token
      expect(response).to have_http_status(:success)
      patch api_v1_account_contact_url(account_id: account.id, id: contact.id), params: { name: 'novo' }, headers: light.create_new_auth_token,
                                                                                as: :json
      expect(response).to have_http_status(:unauthorized)
    end

    it 'relatórios: light (readonly) consulta; agente não' do
      params = { metric: 'conversations_count', type: :account, since: 1.week.ago.to_i.to_s, until: Time.current.to_i.to_s }
      get "/api/v2/accounts/#{account.id}/reports", params: params, headers: light.create_new_auth_token
      expect(response).to have_http_status(:success)
      get "/api/v2/accounts/#{account.id}/reports", params: params, headers: agente.create_new_auth_token
      expect(response).to have_http_status(:unauthorized)
    end

    it 'macro: light não cria' do
      post api_v1_account_macros_url(account_id: account.id),
           params: { name: 'x', visibility: 'personal', actions: [{ action_name: 'add_private_note', action_params: ['oi'] }] },
           headers: light.create_new_auth_token, as: :json
      expect(response).to have_http_status(:forbidden)
      expect(account.macros.count).to eq(0)
    end
  end

  describe 'perfil e suspensão' do
    it 'agente light não altera o próprio nome; agente altera' do
      put '/api/v1/profile', params: { profile: { name: 'Outro Nome' } }, headers: light.create_new_auth_token, as: :json
      expect(response).to have_http_status(:forbidden)
      put '/api/v1/profile', params: { profile: { name: 'Outro Nome' } }, headers: agente.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
    end

    it 'agente suspenso não acessa a conta' do
      agente.account_users.first.update!(suspended_at: Time.current)
      get api_v1_account_conversations_url(account_id: account.id), headers: agente.create_new_auth_token
      expect(response).to have_http_status(:unauthorized)
    end
  end

  describe 'API de papéis (Configurações > Papéis)' do
    it 'lista os 5 papéis padrão do Zendesk e o catálogo' do
      get api_v1_account_sd_roles_url(account_id: account.id), headers: agente.create_new_auth_token
      expect(response).to have_http_status(:success)
      body = response.parsed_body
      expect(body['payload'].pluck('key')).to eq(%w[administrador administrador_faturamento agente agente_light colaborador])
      expect(body['catalog']['keys'].pluck('key')).to include('ticket.comment_public', 'ticket.access')
    end

    it 'administrador cria, edita e exclui papel; agente não' do
      payload = { sd_role: { name: 'Supervisor N2', base_role: 'agent', permissions: { 'reports' => 'readonly', 'ticket.access' => 'groups' } } }
      post api_v1_account_sd_roles_url(account_id: account.id), params: payload, headers: agente.create_new_auth_token, as: :json
      expect(response).to have_http_status(:unauthorized)

      post api_v1_account_sd_roles_url(account_id: account.id), params: payload, headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      role = account.sd_roles.find_by!(key: 'supervisor_n2')
      expect(role.permissions).to include('reports' => 'readonly', 'ticket.access' => 'groups', 'ticket.comment_public' => true)

      patch api_v1_account_sd_role_url(account_id: account.id, id: role.id),
            params: { sd_role: { permissions: { 'ticket.comment_public' => false } } }, headers: admin.create_new_auth_token, as: :json
      expect(role.reload.permissions['ticket.comment_public']).to be(false)

      post api_v1_account_sd_roles_url(account_id: account.id), params: { sd_role: { name: 'Ruim', permissions: { 'reports' => 'tudo' } } },
                                                                headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:unprocessable_entity)

      delete api_v1_account_sd_role_url(account_id: account.id, id: role.id), headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      delete api_v1_account_sd_role_url(account_id: account.id, id: account.sd_roles.find_by!(key: 'agente').id),
             headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:unprocessable_entity)
    end

    it 'administrador troca o papel do agente pela API de agentes e o papel base acompanha' do
      light_role = account.sd_roles.find_by!(key: 'agente_light')
      patch api_v1_account_agent_url(account_id: account.id, id: agente.id), params: { agent: { sd_role_id: light_role.id } },
                                                                             headers: admin.create_new_auth_token, as: :json
      expect(response).to have_http_status(:success)
      expect(response.parsed_body['sd_role_key']).to eq('agente_light')
      expect(response.parsed_body['sd_assignable']).to be(false)

      admin_role = account.sd_roles.find_by!(key: 'administrador')
      patch api_v1_account_agent_url(account_id: account.id, id: agente.id), params: { agent: { sd_role_id: admin_role.id } },
                                                                             headers: admin.create_new_auth_token, as: :json
      expect(account.account_users.find_by!(user: agente).role).to eq('administrator')
    end

    it 'o perfil e GET sd_roles/me trazem o papel, o acesso, os times e as permissões do usuário atual' do
      get '/api/v1/profile', headers: colaborador.create_new_auth_token
      role = response.parsed_body['accounts'].first['servicedesk_role']
      expect(role).to include('role_key' => 'colaborador', 'role_name' => 'Colaborador', 'base_role' => 'agent',
                              'ticket_access' => 'groups', 'team_ids' => [suporte.id], 'zendesk_custom_role_id' => '20487422341915')
      expect(role['permissions']).to include('ticket.comment_public' => false, 'views' => 'readonly', 'contacts.list' => 'none')

      get me_api_v1_account_sd_roles_url(account_id: account.id), headers: light.create_new_auth_token
      expect(response.parsed_body).to include('role_key' => 'agente_light', 'ticket_access' => 'all')
      expect(response.parsed_body['permissions']).to include('reports' => 'readonly', 'macros' => 'readonly')
    end

    it 'o perfil do usuário traz as permissões do papel para o painel' do
      get '/api/v1/profile', headers: light.create_new_auth_token
      permissions = response.parsed_body['accounts'].first['permissions']
      expect(permissions).to include('agent', 'sd_role:agente_light', 'sd:reports:readonly', 'sd:contacts.list')
      expect(permissions).not_to include('sd:ticket.comment_public', 'sd:ticket.edit')
    end
  end
end
