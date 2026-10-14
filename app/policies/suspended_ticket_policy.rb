class SuspendedTicketPolicy < ApplicationPolicy
  def index?
    @account_user.administrator?
  end

  def recover?
    @account_user.administrator?
  end

  def destroy?
    @account_user.administrator?
  end
end
