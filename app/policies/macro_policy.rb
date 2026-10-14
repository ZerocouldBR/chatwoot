# ServiceDesk M13: macros conforme o papel (macro_access do Zendesk).
#   readonly -> só usa as macros compartilhadas (não cria nem edita);
#   personal -> cria e edita as próprias macros pessoais;
#   full     -> também cria e edita as compartilhadas (globais).
# Executar: quem não edita ticket (light/colaborador) só roda macros cujas ações não alteram o ticket
# (ver Servicedesk::Roles::MacroGuard).
class MacroPolicy < ApplicationPolicy
  def index?
    true
  end

  def create?
    sd_access.can?('macros')
  end

  def show?
    @record.global? || author? || group_member?
  end

  def update?
    return sd_access.at_least?('macros', 'full') if @record.global? || @record.team?

    author? && sd_access.can?('macros')
  end

  def destroy?
    return sd_access.at_least?('macros', 'full') if @record.global? || @record.team?

    author? && sd_access.can?('macros')
  end

  def execute?
    (@record.global? || author? || group_member?) && Servicedesk::Roles::MacroGuard.new(@record, sd_access).allowed?
  end

  private

  def group_member?
    @record.team? && @account_user.user.team_ids.include?(@record.team_id)
  end

  def author?
    @record.created_by == @account_user.user
  end
end
