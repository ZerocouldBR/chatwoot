require 'rails_helper'

RSpec.describe Servicedesk::SharedViews do
  let(:account) { create(:account) }
  let(:owner) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:team) { create(:team, account: account, description: 'zendesk_group:100') }
  let(:other_team) { create(:team, account: account, description: 'zendesk_group:200') }
  let(:inbox) { create(:inbox, account: account) }
  let(:open_payload) do
    [{ 'attribute_key' => 'status', 'filter_operator' => 'equal_to', 'values' => ['open'], 'query_operator' => nil }]
  end

  # Como o import_rules_views grava: restrição do Zendesk (tipo + ids dos grupos) e os times já resolvidos
  def shared_view(name, position, type: 'Group', zd_group_ids: [], team_ids: [], payload: []) # rubocop:disable Metrics/ParameterLists
    zendesk = { 'view_id' => "v#{position}", 'titulo' => name, 'posicao' => position,
                'agrupamento' => { 'campo' => 'status', 'ordem' => 'asc' },
                'visibilidade' => { 'tipo' => type, 'zd_group_ids' => zd_group_ids, 'team_ids' => team_ids } }
    create(:custom_filter, account: account, user: owner, filter_type: :conversation, name: name,
                           query: { 'payload' => payload, 'zendesk' => zendesk })
  end

  def names_for(user)
    described_class.new(account: account, user: user).views.pluck(:name)
  end

  def view_named(user, name)
    described_class.new(account: account, user: user).views.find { |view| view[:name] == name }
  end

  before do
    create(:team_member, team: team, user: agent)
    create(:inbox_member, inbox: inbox, user: agent)
    shared_view('Do outro grupo', 30, zd_group_ids: ['200'])
    shared_view('Do meu grupo', 2, zd_group_ids: ['100'], payload: open_payload)
    shared_view('Para todos', 8, type: nil)
    shared_view('Grupo excluido', 9, zd_group_ids: ['999'])
  end

  it 'shows agents only the views of their groups and the unrestricted ones, in the Zendesk order' do
    expect(names_for(agent)).to eq(['Do meu grupo', 'Para todos'])
    expect(view_named(agent, 'Do meu grupo')).to include(shared: true, member: true, owned: false, position: 2)
    expect(view_named(agent, 'Do meu grupo')[:group_by]).to eq('campo' => 'status', 'ordem' => 'asc')
  end

  it 'resolves the group by the team description, so teams created after the import also count' do
    late_team = create(:team, account: account, description: 'zendesk_group:200')
    create(:team_member, team: late_team, user: agent)
    expect(names_for(agent)).to include('Do outro grupo')
  end

  it 'also uses the team ids written by the importer' do
    shared_view('Por id de time', 5, zd_group_ids: ['777'], team_ids: [team.id])
    expect(names_for(agent)).to include('Por id de time')
  end

  it 'ignores users.custom_attributes.zendesk_groups (same team source as the M13 ticket scope)' do
    other = create(:user, account: account, role: :agent, custom_attributes: { 'zendesk_groups' => ['200'] })
    expect(names_for(other)).to eq(['Para todos'])
  end

  it 'shows a User-restricted view only to that user' do
    shared_view('Só do Fulano', 3, type: 'User', zd_group_ids: ['55'])
    fulano = create(:user, account: account, role: :agent, custom_attributes: { 'zendesk_user_id' => '55' })
    expect(names_for(fulano)).to include('Só do Fulano')
    expect(names_for(agent)).not_to include('Só do Fulano')
  end

  it 'shows every view to administrators, flagging the ones outside their groups' do
    expect(names_for(owner)).to eq(['Do meu grupo', 'Para todos', 'Grupo excluido', 'Do outro grupo'])
    expect(view_named(owner, 'Para todos')[:member]).to be(true)
    expect(view_named(owner, 'Do meu grupo')[:member]).to be(false)
  end

  it 'adds the personal filters of the user after the shared ones' do
    create(:custom_filter, account: account, user: agent, filter_type: :conversation, name: 'Minha',
                           query: { 'payload' => open_payload })
    expect(described_class.new(account: account, user: agent).views.last).to include(name: 'Minha', shared: false, owned: true)
  end

  it 'deduplicates views imported twice' do
    shared_view('Do meu grupo', 2, zd_group_ids: ['100'])
    expect(names_for(owner).count('Do meu grupo')).to eq(1)
  end

  it 'counts tickets with the filter and the permissions of the user' do
    create(:conversation, account: account, inbox: inbox, status: :open)
    create(:conversation, account: account, inbox: inbox, status: :resolved)
    create(:conversation, account: account, inbox: create(:inbox, account: account), status: :open)

    agent_counts = described_class.new(account: account, user: agent).counts
    expect(agent_counts[view_named(agent, 'Do meu grupo')[:id]]).to eq(1)
    expect(agent_counts[view_named(agent, 'Para todos')[:id]]).to eq(2)

    admin_counts = described_class.new(account: account, user: owner).counts
    expect(admin_counts[view_named(owner, 'Do meu grupo')[:id]]).to eq(2)
    expect(admin_counts[view_named(owner, 'Para todos')[:id]]).to eq(3)
  end

  it 'returns nil for a view whose filter cannot run' do
    shared_view('Quebrada', 1, type: nil,
                               payload: [{ 'attribute_key' => 'nao_existe', 'filter_operator' => 'equal_to', 'values' => ['x'] }])
    counts = described_class.new(account: account, user: owner).counts
    expect(counts[view_named(owner, 'Quebrada')[:id]]).to be_nil
  end
end
