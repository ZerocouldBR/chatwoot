require 'rails_helper'

RSpec.describe PortalCustomers::RequestStatus do
  let(:account) { create(:account) }

  def conversation(status, zd_status = nil, sistema = nil)
    build(:conversation, account: account, status: status,
                         custom_attributes: { 'zd_status' => zd_status, 'zd_status_sistema' => sistema }.compact)
  end

  it 'usa o rótulo do usuário final do Zendesk quando zd_status bate com o status nativo' do
    expect(described_class.new(conversation(:open, 'Novo')).label).to eq('Aberto')
    expect(described_class.new(conversation(:open, 'Em andamento')).label).to eq('Em andamento')
    expect(described_class.new(conversation(:waiting_on_customer, 'Pendente')).label).to eq('Aguardando resposta')
    expect(described_class.new(conversation(:on_hold, 'Aguardando Desenvolvimento')).label).to eq('Aberto')
    expect(described_class.new(conversation(:on_hold, 'Retorno Integrações ')).label).to eq('Retorno Integrações')
    expect(described_class.new(conversation(:resolved, 'Respondido cliente')).label).to eq('Respondido cliente')
  end

  it 'agrupa como os filtros do Zendesk: em espera conta como aberto, pendente como aguardando' do
    expect(described_class.new(conversation(:on_hold, 'Desenvolvimento')).group).to eq('open')
    expect(described_class.new(conversation(:waiting_on_customer, 'Pendente')).group).to eq('awaiting')
    expect(described_class.new(conversation(:waiting_on_customer)).group).to eq('awaiting')
  end

  it 'agrupa os status nativos sem rótulo do Zendesk' do
    groups = %i[pending new_ticket on_hold closed].map { |status| described_class.new(conversation(status)).group }
    expect(groups).to eq(%w[open open open solved])
  end

  it 'resolvido fica em Resolvido' do
    expect(described_class.new(conversation(:resolved)).group).to eq('solved')
  end

  it 'ignora zd_status desatualizado (agente mudou o status direto no painel)' do
    status = described_class.new(conversation(:resolved, 'Pendente'))
    expect(status.group).to eq('solved')
    expect(status.label).to eq(I18n.t('public_portal.sd.requests.status.solved'))
  end

  it 'reconhece ticket fechado pelo status nativo closed' do
    expect(described_class.new(conversation(:closed, 'Resolvido', 'Fechado'))).to be_closed
    expect(described_class.new(conversation(:closed, 'Fechado')).label).to eq('Resolvido')
    expect(described_class.new(conversation(:resolved, 'Resolvido', 'Fechado'))).not_to be_closed
  end

  it 'filtra no banco pelos status nativos de cada grupo' do
    ids = Conversation.statuses.keys.index_with do |status|
      record = create(:conversation, account: account)
      record.update_columns(status: Conversation.statuses[status]) # rubocop:disable Rails/SkipsModelValidations
      record.id
    end
    relation = Conversation.where(account: account)
    expect(described_class.filter(relation, 'open').pluck(:id)).to match_array(ids.values_at('new_ticket', 'open', 'pending', 'on_hold'))
    expect(described_class.filter(relation, 'awaiting').pluck(:id)).to eq([ids['waiting_on_customer']])
    expect(described_class.filter(relation, 'solved').pluck(:id)).to match_array(ids.values_at('resolved', 'closed'))
    expect(described_class.filter(relation, 'xyz').count).to eq(ids.size)
  end
end
