# frozen_string_literal: true

require 'rails_helper'

# ServiceDesk M13: escopos de listagem (lista de tickets, filtros, busca) conforme ticket.access do papel.
RSpec.describe Servicedesk::Roles::TicketScope do
  let(:account) { create(:account) }
  let!(:ticket_suporte) { create(:conversation, account: account, inbox: inbox, team: suporte) }
  let!(:ticket_ti) { create(:conversation, account: account, inbox: inbox, team: ti) }
  let!(:ticket_sem_grupo) { create(:conversation, account: account, inbox: inbox, team: nil) }
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

  def visible(user)
    Conversations::PermissionFilterService.new(account.conversations, user, account).perform.pluck(:id)
  end

  it 'administrador vê todos os tickets' do
    admin = member('administrador', base: :administrator)
    expect(visible(admin)).to contain_exactly(ticket_suporte.id, ticket_ti.id, ticket_sem_grupo.id)
  end

  it 'agente e agente light (acesso a todos) veem todos os tickets das inboxes' do
    expect(visible(member('agente', teams: [suporte]))).to contain_exactly(ticket_suporte.id, ticket_ti.id, ticket_sem_grupo.id)
    expect(visible(member('agente_light', teams: [suporte]))).to contain_exactly(ticket_suporte.id, ticket_ti.id, ticket_sem_grupo.id)
  end

  it 'agente de grupo (colaborador) não vê ticket de outro grupo nem sem grupo' do
    colaborador = member('colaborador', teams: [suporte])
    expect(visible(colaborador)).to contain_exactly(ticket_suporte.id)
  end

  it 'agente de grupo vê ticket de outro grupo atribuído a ele ou em que participa' do
    colaborador = member('colaborador', teams: [suporte])
    ticket_ti.update!(assignee: colaborador)
    create(:conversation_participant, conversation: ticket_sem_grupo, user: colaborador, account: account)
    expect(visible(colaborador)).to contain_exactly(ticket_suporte.id, ticket_ti.id, ticket_sem_grupo.id)
  end

  it 'ConversationFinder (lista e contadores) respeita o grupo' do
    colaborador = member('colaborador', teams: [ti])
    Current.account = account
    result = ConversationFinder.new(colaborador, { assignee_type: 'all', status: 'open' }.with_indifferent_access).perform
    expect(result[:conversations].map(&:id)).to contain_exactly(ticket_ti.id)
    expect(result[:count][:all_count]).to eq(1)
  ensure
    Current.reset
  end

  it 'busca de tickets e de mensagens respeita o grupo' do
    colaborador = member('colaborador', teams: [ti])
    Current.account = account
    create(:message, conversation: ticket_suporte, account: account, inbox: inbox, content: 'reserva cancelada suporte')
    create(:message, conversation: ticket_ti, account: account, inbox: inbox, content: 'reserva cancelada ti')
    search = SearchService.new(current_user: colaborador, current_account: account, params: { q: 'reserva' }, search_type: 'Message')
    expect(search.perform[:messages].map(&:conversation_id)).to contain_exactly(ticket_ti.id)

    search = SearchService.new(current_user: colaborador, current_account: account,
                               params: { q: ticket_suporte.display_id.to_s }, search_type: 'Conversation')
    expect(search.perform[:conversations].map(&:id)).not_to include(ticket_suporte.id)
  ensure
    Current.reset
  end

  it 'busca de contatos vazia para quem não tem acesso à lista de usuários finais' do
    colaborador = member('colaborador', teams: [ti])
    create(:contact, account: account, name: 'Hotel Exemplo')
    search = SearchService.new(current_user: colaborador, current_account: account, params: { q: 'Hotel' }, search_type: 'Contact')
    expect(search.perform[:contacts]).to be_empty
  end

  it 'eventos em tempo real só vão para quem pode ver o ticket' do
    colaborador = member('colaborador', teams: [ti])
    light = member('agente_light', teams: [ti])
    members = described_class.visible_members(ticket_suporte)
    expect(members).to include(light)
    expect(members).not_to include(colaborador)
    expect(described_class.visible_members(ticket_ti)).to include(colaborador)
  end

  it 'acesso "requested": só os tickets em que o próprio agente é o solicitante' do
    agente = member('agente', teams: [ti])
    agente.account_users.first.update!(ticket_access_override: 'requested')
    own = create(:conversation, account: account, inbox: inbox, contact: create(:contact, account: account, email: agente.email))
    expect(visible(agente)).to contain_exactly(own.id)
  end
end
