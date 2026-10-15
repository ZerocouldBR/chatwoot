# ServiceDesk M13: a tela/API "Papéis" é do administrador (manage_roles do Zendesk). Qualquer agente pode listar os
# papéis (o painel mostra o nome do papel), mas só o administrador cria, edita ou exclui.
class SdRolePolicy < ApplicationPolicy
  def index?
    true
  end

  def show?
    true
  end

  def me?
    true
  end

  def create?
    @account_user.administrator?
  end

  def update?
    @account_user.administrator?
  end

  def destroy?
    @account_user.administrator?
  end
end
