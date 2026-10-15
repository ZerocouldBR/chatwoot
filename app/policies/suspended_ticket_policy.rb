# ServiceDesk M13: tickets suspensos com o administrador ou o papel com suspended_tickets.manage (Zendesk).
class SuspendedTicketPolicy < ApplicationPolicy
  def index?
    manage?
  end

  def recover?
    manage?
  end

  def destroy?
    manage?
  end

  private

  def manage?
    @account_user.administrator? || Servicedesk::Roles::Access.for(@account_user).can?('suspended_tickets.manage')
  end
end
