# ServiceDesk M13: views (filtros salvos). 'readonly' só usa as views; 'personal'/'full' criam e editam as suas.
class CustomFilterPolicy < ApplicationPolicy
  def create?
    @account_user.administrator? || (@account_user.agent? && sd_access.can?('views'))
  end

  def show?
    @account_user.administrator? || @account_user.agent?
  end

  def index?
    @account_user.administrator? || @account_user.agent?
  end

  def update?
    @account_user.administrator? || (@account_user.agent? && sd_access.can?('views'))
  end

  def destroy?
    @account_user.administrator? || (@account_user.agent? && sd_access.can?('views'))
  end
end
