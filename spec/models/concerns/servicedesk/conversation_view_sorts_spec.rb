require 'rails_helper'

# Ordenações das views do Zendesk (execution.sort_by) pela Conversations::SortService, sobre o modelo do Victor
RSpec.describe Servicedesk::ConversationViewSorts do
  let(:account) { create(:account) }
  let(:inbox_a) { create(:inbox, account: account, name: 'Atendimento') }
  let(:inbox_b) { create(:inbox, account: account, name: 'Financeiro') }
  let(:team_a) { create(:team, account: account, name: 'Cadastro') }
  let(:team_b) { create(:team, account: account, name: 'Suporte') }

  def ticket(**attributes)
    create(:conversation, account: account, inbox: attributes.delete(:inbox) || inbox_a, **attributes)
  end

  def sorted(sort_by)
    Conversations::SortService.apply(account.conversations, sort_by).to_a
  end

  it 'ordena pelo ID do ticket (display_id)' do
    first = ticket
    second = ticket
    expect(sorted('sd_id_asc')).to eq([first, second])
    expect(sorted('sd_id_desc')).to eq([second, first])
  end

  it 'ordena pelo grupo, com os tickets sem grupo no fim nas duas direções' do
    suporte = ticket(team: team_b)
    sem_grupo = ticket
    cadastro = ticket(team: team_a)
    expect(sorted('sd_group_asc')).to eq([cadastro, suporte, sem_grupo])
    expect(sorted('sd_group_desc')).to eq([suporte, cadastro, sem_grupo])
  end

  it 'ordena pelo solicitante, pelo canal e pelo assunto' do
    zeca = ticket(contact: create(:contact, account: account, name: 'Zeca'), inbox: inbox_a, subject: 'boleto')
    ana = ticket(contact: create(:contact, account: account, name: 'ana'), inbox: inbox_b, subject: 'Acesso')
    expect(sorted('sd_requester_asc')).to eq([ana, zeca])
    expect(sorted('sd_channel_asc')).to eq([zeca, ana])
    expect(sorted('sd_channel_desc')).to eq([ana, zeca])
    expect(sorted('sd_subject_asc')).to eq([ana, zeca])
  end

  it 'ordena pela categoria do status do Zendesk (enum do Victor)' do
    resolvido = ticket(status: :resolved)
    em_espera = ticket(status: :on_hold)
    pendente = ticket(status: :waiting_on_customer)
    novo = ticket(status: :new_ticket)
    aberto = ticket(status: :open)

    expect(sorted('sd_status_asc')).to eq([novo, aberto, pendente, em_espera, resolvido])
  end

  it 'ordena pelo SLA (próxima violação), sem SLA no fim' do
    sem_sla = ticket
    depois = ticket
    antes = ticket
    depois.update_columns(next_sla_breach_at: 2.hours.from_now) # rubocop:disable Rails/SkipsModelValidations
    antes.update_columns(next_sla_breach_at: 1.hour.from_now) # rubocop:disable Rails/SkipsModelValidations
    expect(sorted('sd_sla_asc')).to eq([antes, depois, sem_sla])
  end

  it 'ordena por resolvido em (auditoria) e pela atualização do solicitante (mensagens)' do
    antigo = ticket(status: :open)
    recente = ticket(status: :open)
    aberto = ticket(status: :open)
    travel_to(3.days.ago) { antigo.update!(status: :resolved) }
    travel_to(1.day.ago) { recente.update!(status: :resolved) }
    create(:message, conversation: antigo, account: account, inbox: inbox_a, message_type: :incoming, created_at: 1.hour.ago)
    create(:message, conversation: recente, account: account, inbox: inbox_a, message_type: :incoming, created_at: 2.days.ago)

    expect(sorted('sd_solved_desc')).to eq([recente, antigo, aberto])
    expect(sorted('sd_requester_updated_desc')).to eq([antigo, recente, aberto])

    clocks = Servicedesk::TicketClocks.preload(account.conversations.where(id: [antigo.id, recente.id])).to_a
    clock = clocks.find { |c| c.id == recente.id }.sd_clock
    expect(clock[:solved_at]).to be_within(5).of(1.day.ago.to_i)
    expect(clock[:requester_updated_at]).to be_within(5).of(2.days.ago.to_i)
  end

  it 'mantém as ordenações nativas e a padrão para chaves desconhecidas' do
    older = ticket(created_at: 2.days.ago)
    newer = ticket(created_at: 1.day.ago)
    expect(sorted('created_at_asc')).to eq([older, newer])
    expect(sorted('nao_existe').size).to eq(2)
  end

  it 'funciona sobre a busca de views (FilterService), com o escopo do agente' do
    admin = create(:user, account: account, role: :administrator)
    second = ticket(team: team_b, status: :open)
    first = ticket(team: team_a, status: :open)
    params = { payload: [{ attribute_key: 'status', filter_operator: 'equal_to', values: ['open'], query_operator: nil }],
               sort_by: 'sd_group_asc' }.with_indifferent_access
    result = Conversations::FilterService.new(params, admin, account).perform
    expect(result[:conversations].to_a).to eq([first, second])
  end
end
