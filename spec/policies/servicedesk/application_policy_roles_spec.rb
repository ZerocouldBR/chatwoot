# frozen_string_literal: true

require 'rails_helper'

# ServiceDesk M13: matriz papel x permissão nas policies (papéis padrão do Zendesk semeados na conta).
# ServiceDesk M13: policies conforme o papel do Zendesk (Administrador, Agente, Agente light, Colaborador)
RSpec.describe ApplicationPolicy, type: :policy do
  let(:account) { create(:account) }
  let(:admin) { member_with('administrador', base: :administrator) }
  let(:agente) { member_with('agente', teams: [team]) }
  let(:light) { member_with('agente_light', teams: [team]) }
  let(:colaborador) { member_with('colaborador', teams: [team]) }
  let(:ce_agent) { member_with(nil) }
  let(:own_team_ticket) { create(:conversation, account: account, inbox: inbox, team: team) }
  let(:other_team_ticket) { create(:conversation, account: account, inbox: inbox, team: other_team) }
  let(:inbox) { create(:inbox, account: account) }
  let(:team) { create(:team, account: account) }
  let(:other_team) { create(:team, account: account) }

  def member_with(role_key, base: :agent, teams: [])
    user = create(:user, account: account, role: base)
    account_user = account.account_users.find_by!(user: user)
    account_user.update!(sd_role: role_key && account.sd_roles.find_by!(key: role_key))
    create(:inbox_member, inbox: inbox, user: user)
    teams.each { |t| create(:team_member, team: t, user: user) }
    account_user.reload
  end

  def context_for(account_user)
    { user: account_user.user, account: account, account_user: account_user }
  end

  describe ConversationPolicy do
    let(:policy) { described_class }

    it 'administrador vê tudo e exclui' do
      expect(policy.new(context_for(admin), other_team_ticket).show?).to be(true)
      expect(policy.new(context_for(admin), other_team_ticket).destroy?).to be(true)
    end

    it 'agente vê todos os tickets, responde em público, edita e exclui (como no Zendesk)' do
      p = policy.new(context_for(agente), other_team_ticket)
      expect([p.show?, p.reply_public?, p.edit_ticket?, p.edit_tags?, p.destroy?]).to all(be(true))
      expect(p.redact_message?).to be(false)
    end

    it 'agente light vê todos os tickets, mas não responde em público, não edita e não exclui' do
      p = policy.new(context_for(light), other_team_ticket)
      expect(p.show?).to be(true)
      expect([p.reply_public?, p.edit_ticket?, p.edit_tags?, p.destroy?, p.redact_message?]).to all(be(false))
    end

    it 'colaborador (acesso por grupo) não vê ticket de outro grupo' do
      expect(policy.new(context_for(colaborador), own_team_ticket).show?).to be(true)
      expect(policy.new(context_for(colaborador), other_team_ticket).show?).to be(false)
    end

    it 'colaborador vê ticket de outro grupo quando é o responsável ou participante' do
      assigned = create(:conversation, account: account, inbox: inbox, team: other_team)
      assigned.update!(assignee: colaborador.user)
      followed = create(:conversation, account: account, inbox: inbox, team: other_team)
      create(:conversation_participant, conversation: followed, user: colaborador.user, account: account)
      expect(policy.new(context_for(colaborador), assigned).show?).to be(true)
      expect(policy.new(context_for(colaborador), followed).show?).to be(true)
    end

    it 'restrição do usuário (ticket_restriction=groups do Zendesk) vale mesmo com papel Agente' do
      agente.update!(ticket_access_override: 'groups')
      expect(policy.new(context_for(agente), own_team_ticket).show?).to be(true)
      expect(policy.new(context_for(agente), other_team_ticket).show?).to be(false)
    end

    it 'only_private_comments do usuário tira a resposta pública' do
      agente.update!(only_private_comments: true)
      expect(policy.new(context_for(agente), own_team_ticket).reply_public?).to be(false)
    end

    it 'agente sem papel SD mantém o comportamento do Chatwoot CE' do
      p = policy.new(context_for(ce_agent), other_team_ticket)
      expect([p.show?, p.reply_public?, p.edit_ticket?, p.redact_message?]).to all(be(true))
      expect(p.destroy?).to be(false)
    end
  end

  describe ContactPolicy do
    let(:contact) { create(:contact, account: account) }

    it 'lista de usuários finais: colaborador não vê (contacts.list=none), mas abre o perfil' do
      expect(described_class.new(context_for(colaborador), contact).index?).to be(false)
      expect(described_class.new(context_for(colaborador), contact).search?).to be(false)
      expect(described_class.new(context_for(colaborador), contact).show?).to be(true)
    end

    it 'light vê a lista e não edita; agente edita; admin exclui' do
      expect(described_class.new(context_for(light), contact).index?).to be(true)
      expect(described_class.new(context_for(light), contact).update?).to be(false)
      expect(described_class.new(context_for(light), contact).create?).to be(false)
      expect(described_class.new(context_for(agente), contact).update?).to be(true)
      expect(described_class.new(context_for(admin), contact).destroy?).to be(true)
    end
  end

  describe CompanyPolicy do
    it 'só edita organizações quem tem organizations.edit' do
      company = Company.new(account: account)
      expect(described_class.new(context_for(admin), company).update?).to be(true)
      expect(described_class.new(context_for(agente), company).update?).to be(false)
      expect(described_class.new(context_for(light), company).create?).to be(false)
      expect(described_class.new(context_for(ce_agent), company).create?).to be(true)
    end
  end

  describe ReportPolicy do
    it 'relatórios: admin e agente light (readonly) veem; agente e colaborador não' do
      expect(described_class.new(context_for(admin), :report).view?).to be(true)
      expect(described_class.new(context_for(light), :report).view?).to be(true)
      expect(described_class.new(context_for(agente), :report).view?).to be(false)
      expect(described_class.new(context_for(colaborador), :report).view?).to be(false)
    end
  end

  describe MacroPolicy do
    let(:global_macro) { create(:macro, account: account, visibility: :global, created_by: admin.user) }
    let(:note_macro) do
      create(:macro, account: account, visibility: :global, created_by: admin.user,
                     actions: [{ 'action_name' => 'add_private_note', 'action_params' => ['nota'] }])
    end

    it 'light (readonly) não cria macros; agente (personal) cria só pessoais; admin (full) edita compartilhadas' do
      expect(described_class.new(context_for(light), Macro.new).create?).to be(false)
      expect(described_class.new(context_for(agente), Macro.new).create?).to be(true)
      expect(described_class.new(context_for(agente), global_macro).update?).to be(false)
      expect(described_class.new(context_for(admin), global_macro).update?).to be(true)
    end

    it 'light só aplica macro que não altera o ticket' do
      expect(described_class.new(context_for(light), global_macro).execute?).to be(false) # add_label
      expect(described_class.new(context_for(light), note_macro).execute?).to be(true)
      expect(described_class.new(context_for(agente), global_macro).execute?).to be(true)
    end
  end

  describe CustomFilterPolicy do
    it 'views: readonly não cria; personal cria' do
      filter = CustomFilter.new(account: account)
      expect(described_class.new(context_for(light), filter).create?).to be(false)
      expect(described_class.new(context_for(colaborador), filter).create?).to be(false)
      expect(described_class.new(context_for(agente), filter).create?).to be(true)
      expect(described_class.new(context_for(light), filter).index?).to be(true)
    end
  end

  describe SdRolePolicy do
    it 'só o administrador cria e edita papéis' do
      role = account.sd_roles.first
      expect(described_class.new(context_for(admin), role).update?).to be(true)
      expect(described_class.new(context_for(agente), role).update?).to be(false)
      expect(described_class.new(context_for(agente), SdRole).index?).to be(true)
    end
  end
end
