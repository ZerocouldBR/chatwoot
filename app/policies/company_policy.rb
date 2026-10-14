# ServiceDesk M13: organizações (empresas) só são editadas com organizations.edit.
class CompanyPolicy < ApplicationPolicy
  def index?
    true
  end

  def search?
    true
  end

  def show?
    true
  end

  def create?
    sd_access.can?('organizations.edit')
  end

  def update?
    sd_access.can?('organizations.edit')
  end

  def avatar?
    update?
  end

  def destroy_custom_attributes?
    update?
  end

  def destroy?
    @account_user.administrator?
  end
end

CompanyPolicy.prepend_mod_with('CompanyPolicy')
