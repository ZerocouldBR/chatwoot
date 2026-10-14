# ServiceDesk M13: lista de usuários finais (contacts.list) e edição (contacts.edit), como no Zendesk.
class ContactPolicy < ApplicationPolicy
  def index?
    sd_access.can?('contacts.list')
  end

  def active?
    sd_access.can?('contacts.list')
  end

  def import?
    @account_user.administrator?
  end

  def export?
    @account_user.administrator?
  end

  def search?
    sd_access.can?('contacts.list')
  end

  def filter?
    sd_access.can?('contacts.list')
  end

  def update?
    sd_access.can?('contacts.edit')
  end

  def contactable_inboxes?
    true
  end

  def destroy_custom_attributes?
    sd_access.can?('contacts.edit')
  end

  def show?
    true
  end

  def create?
    sd_access.can?('contacts.edit')
  end

  def avatar?
    sd_access.can?('contacts.edit')
  end

  def destroy?
    @account_user.administrator?
  end
end

ContactPolicy.prepend_mod_with('ContactPolicy')
