class MacroPolicy < ApplicationPolicy
  def index?
    true
  end

  def create?
    true
  end

  def show?
    @record.global? || author? || group_member?
  end

  def update?
    return @account_user.administrator? if @record.global? || @record.team?

    author?
  end

  def destroy?
    return @account_user.administrator? if @record.global? || @record.team?

    author?
  end

  def execute?
    @record.global? || author? || group_member?
  end

  private

  def group_member?
    @record.team? && @account_user.user.team_ids.include?(@record.team_id)
  end

  def author?
    @record.created_by == @account_user.user
  end
end
