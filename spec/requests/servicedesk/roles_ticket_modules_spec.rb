# frozen_string_literal: true

require 'rails_helper'

# ServiceDesk M13 sobre a base do Victor (f3..f8): mesclar, spam, redação, CCs, lixeira e suspensos conforme o papel,
# e visibilidade dos tickets em que o agente está em cópia (CC).
RSpec.describe 'ServiceDesk M13 - papéis nos módulos de ticket do Victor', type: :request do
  let(:account) { create(:account) }
  let(:inbox) { create(:inbox, account: account) }
  let(:suporte) { create(:team, account: account, name: 'Suporte') }
  let(:ti) { create(:team, account: account, name: 'TI - N2') }
  let(:admin) { member('administrador', base: :administrator) }
  let(:agente) { member('agente', teams: [suporte]) }
  let(:light) { member('agente_light', teams: [suporte]) }
  let(:colaborador) { member('colaborador', teams: [suporte]) }
  let(:ticket) { create(:conversation, account: account, inbox: inbox, team: suporte, status: :open) }
  let(:other) { create(:conversation, account: account, inbox: inbox, team: suporte, status: :open) }

  def member(role_key, base: :agent, teams: [])
    user = create(:user, account: account, role: base)
    account.account_users.find_by!(user: user).update!(sd_role: account.sd_roles.find_by!(key: role_key))
    create(:inbox_member, inbox: inbox, user: user)
    teams.each { |t| create(:team_member, team: t, user: user) }
    user
  end

  def conversation_url(conversation, path)
    "/api/v1/accounts/#{account.id}/conversations/#{conversation.display_id}/#{path}"
  end

  it 'mesclar: agente (ticket.merge) mescla; agente light recebe 403' do
    post conversation_url(ticket, 'merge'), params: { target_id: other.display_id }, headers: light.create_new_auth_token, as: :json
    expect(response).to have_http_status(:forbidden)
    expect(response.parsed_body['servicedesk_role']).to be(true)

    post conversation_url(ticket, 'merge'), params: { target_id: other.display_id }, headers: agente.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
  end

  it 'spam: agente (ticket.delete) marca; colaborador recebe 403' do
    post conversation_url(ticket, 'spam'), headers: colaborador.create_new_auth_token, as: :json
    expect(response).to have_http_status(:forbidden)
    expect(ticket.reload.deleted_at).to be_nil

    post conversation_url(ticket, 'spam'), headers: agente.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(Conversation.trashed.find(ticket.id).deleted_at).to be_present
  end

  it 'CCs: light não altera a lista de cópia; agente altera' do
    post conversation_url(ticket, 'ccs'), params: { email: 'cliente2@example.com' }, headers: light.create_new_auth_token, as: :json
    expect(response).to have_http_status(:forbidden)

    post conversation_url(ticket, 'ccs'), params: { email: 'cliente2@example.com' }, headers: agente.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(response.parsed_body['payload']).to eq(['cliente2@example.com'])
    expect(ConversationCc.where(conversation_id: ticket.id).pluck(:email)).to eq(['cliente2@example.com'])
  end

  it 'redação: agente (sem ticket.redact) recebe 403; administrador redige' do
    message = create(:message, conversation: ticket, account: account, inbox: inbox, content: 'cartão 4111 1111')
    url = conversation_url(ticket, "messages/#{message.id}/redaction")
    post url, params: { text: '4111' }, headers: agente.create_new_auth_token, as: :json
    expect(response).to have_http_status(:forbidden)

    post url, params: { text: '4111' }, headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
  end

  it 'lixeira: só quem tem ticket.view_deleted lista e restaura' do
    ticket.trash!
    get "/api/v1/accounts/#{account.id}/deleted_tickets", headers: agente.create_new_auth_token, as: :json
    expect(response).to have_http_status(:forbidden)

    get "/api/v1/accounts/#{account.id}/deleted_tickets", headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(response.parsed_body['payload'].pluck('id')).to eq([ticket.display_id])
  end

  it 'suspensos: papel com suspended_tickets.manage (agente light no Zendesk da B2B) lista; agente não' do
    get "/api/v1/accounts/#{account.id}/suspended_tickets", headers: agente.create_new_auth_token, as: :json
    expect(response).not_to have_http_status(:success)

    get "/api/v1/accounts/#{account.id}/suspended_tickets", headers: light.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
  end

  it 'regras, SLA e horários: só o administrador altera' do
    post "/api/v1/accounts/#{account.id}/ticket_rules", params: { kind: 'trigger', ticket_rule: { title: 'x' } },
                                                        headers: agente.create_new_auth_token, as: :json
    expect(response).not_to have_http_status(:success)
    expect(TicketRule.where(account: account).count).to eq(0)
  end

  it 'colaborador vê ticket de outro grupo quando está em cópia (CC), como no Zendesk' do
    ticket_ti = create(:conversation, account: account, inbox: inbox, team: ti, status: :open)
    get "/api/v1/accounts/#{account.id}/conversations/#{ticket_ti.display_id}", headers: colaborador.create_new_auth_token, as: :json
    expect(response).to have_http_status(:unauthorized)

    ConversationCc.create!(account: account, conversation: ticket_ti, email: colaborador.email)
    get "/api/v1/accounts/#{account.id}/conversations/#{ticket_ti.display_id}", headers: colaborador.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)

    scope = Conversations::PermissionFilterService.new(account.conversations, colaborador, account).perform
    expect(scope.pluck(:id)).to include(ticket_ti.id)
  end
end
