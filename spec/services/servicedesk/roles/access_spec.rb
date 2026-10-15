# frozen_string_literal: true

require 'rails_helper'

RSpec.describe Servicedesk::Roles::Access do
  let(:account) { create(:account) }

  def account_user_with(role_key, base: :agent)
    user = create(:user, account: account, role: base)
    account_user = account.account_users.find_by!(user: user)
    account_user.update!(sd_role: role_key && account.sd_roles.find_by!(key: role_key))
    account_user
  end

  it 'a conta nova já nasce com os 5 papéis padrão do Zendesk' do
    expect(account.sd_roles.ordered.pluck(:key, :base_role)).to eq(
      [%w[administrador administrator], %w[administrador_faturamento administrator], %w[agente agent],
       %w[agente_light agent], %w[colaborador agent]]
    )
    expect(account.sd_roles.find_by!(key: 'agente_light').zendesk_custom_role_id).to eq(20_487_384_045_211)
  end

  it 'o seeder é idempotente e não sobrescreve papel editado (a não ser com reset)' do
    role = account.sd_roles.find_by!(key: 'agente_light')
    role.update!(permissions: role.permissions.merge('reports' => 'none'))
    expect { Servicedesk::Roles::Seeder.new(account).perform }.not_to change(SdRole, :count)
    expect(role.reload.permissions['reports']).to eq('none')
    Servicedesk::Roles::Seeder.new(account).perform(reset: true)
    expect(role.reload.permissions['reports']).to eq('readonly')
  end

  it 'escolher o papel define o papel base do account_user' do
    account_user = account_user_with('administrador')
    expect(account_user.reload.role).to eq('administrator')
    account_user.update!(sd_role: account.sd_roles.find_by!(key: 'colaborador'))
    expect(account_user.reload.role).to eq('agent')
  end

  it 'mudar o papel base pela tela padrão do CE descarta o papel SD incompatível' do
    account_user = account_user_with('agente_light')
    account_user.update!(role: :administrator)
    expect(account_user.reload.sd_role).to be_nil
    expect(account_user.sd_access.can?('ticket.comment_public')).to be(true)
  end

  it 'papel de outra conta é recusado' do
    other = create(:account)
    account_user = account_user_with('agente')
    expect { account_user.update!(sd_role: other.sd_roles.first) }.to raise_error(ActiveRecord::RecordInvalid)
  end

  it 'papel de administrador sempre tem tudo liberado' do
    role = account.sd_roles.find_by!(key: 'administrador')
    role.update!(permissions: { 'reports' => 'none' })
    expect(role.reload.permissions['reports']).to eq('full')
  end

  it 'valores inválidos são recusados' do
    role = account.sd_roles.new(key: 'x_1', name: 'X', permissions: { 'reports' => 'tudo', 'nao_existe' => true })
    expect(role).not_to be_valid
    expect(role.errors[:permissions].first).to include('reports', 'nao_existe')
  end

  it 'agente sem papel SD = Chatwoot CE (CE_AGENT)' do
    access = account_user_with(nil).sd_access
    expect(access.permissions).to eq(Servicedesk::Roles::Catalog::CE_AGENT)
  end

  it 'o mapa de permissões do painel (fixture do vitest) é exatamente o que o backend envia' do
    fixture_path = Rails.root.join('app/javascript/dashboard/servicedesk/roles/specs/fixtures/rolePermissions.json')
    fixture = JSON.parse(File.read(fixture_path))
    actual = {
      'administrador' => account_user_with('administrador', base: :administrator).permissions,
      'agente' => account_user_with('agente').permissions,
      'agente_light' => account_user_with('agente_light').permissions,
      'colaborador' => account_user_with('colaborador').permissions,
      'sem_papel' => account_user_with(nil).permissions
    }
    expect(actual).to eq(fixture)
  end
end
