class ConversationPolicy < ApplicationPolicy
  def index?
    true
  end

  # ServiceDesk M13: excluir ticket conforme o papel (o Zendesk deixa o Agente excluir; o CE só o administrador)
  def destroy?
    administrator? || sd_access.can?('ticket.delete')
  end

  def show?
    administrator? || agent_bot? || agent_can_view_conversation?
  end

  # ---- ServiceDesk M13: ações sobre o ticket, conforme o papel (usadas por Servicedesk::RoleEnforcement)
  def reply_public?
    sd_user_can?('ticket.comment_public')
  end

  def edit_ticket?
    sd_user_can?('ticket.edit')
  end

  def edit_tags?
    sd_user_can?('ticket.edit_tags')
  end

  def redact_message?
    sd_user_can?('ticket.redact')
  end

  # Módulos do Victor: mesclar tickets, lixeira (ver/restaurar) e excluir/marcar como spam
  def merge_ticket?
    sd_user_can?('ticket.merge')
  end

  def view_deleted?
    sd_user_can?('ticket.view_deleted')
  end

  def delete_ticket?
    sd_user_can?('ticket.delete')
  end

  private

  def agent_can_view_conversation?
    (inbox_access? || team_access?) && sd_ticket_allowed?
  end

  def sd_access
    Servicedesk::Roles::Access.for(account_user)
  end

  def sd_user_can?(key)
    return true if agent_bot? || administrator?

    sd_access.can?(key)
  end

  def sd_ticket_allowed?
    Servicedesk::Roles::TicketScope.new(user, account, account_user: account_user).allowed?(record)
  end

  def administrator?
    account_user&.administrator?
  end

  def agent_bot?
    user.is_a?(AgentBot)
  end

  def inbox_access?
    user.inboxes.where(account_id: account&.id).exists?(id: record.inbox_id)
  end

  def team_access?
    return false if record.team_id.blank?

    user.teams.where(account_id: account&.id).exists?(id: record.team_id)
  end

  def assigned_to_user?
    record.assignee_id == user.id
  end

  def participant?
    record.conversation_participants.exists?(user_id: user.id)
  end
end

ConversationPolicy.prepend_mod_with('ConversationPolicy')
