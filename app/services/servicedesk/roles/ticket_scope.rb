# ServiceDesk M13: restrição de visibilidade de tickets por papel (ticket.access), aplicada DEPOIS do filtro nativo
# por inbox. O CE só filtra por inbox; aqui entra o "acesso aos tickets" do Zendesk:
#   all       -> sem filtro adicional
#   groups    -> time da conversa entre os times do usuário OU responsável = usuário OU seguidor OU em cópia (CC)
#   assigned  -> responsável = usuário OU seguidor OU em cópia (CC, conversation_ccs do Victor, pelo e-mail)
#   requested -> contato da conversa com o mesmo e-mail do usuário (tickets que ele mesmo abriu)
# Administrador e AgentBot nunca são restringidos.
class Servicedesk::Roles::TicketScope
  def initialize(user, account, account_user: nil)
    @user = user
    @account = account
    @account_user = account_user
  end

  def self.apply(conversations, user, account, account_user: nil)
    new(user, account, account_user: account_user).apply(conversations)
  end

  def access
    @access ||= Servicedesk::Roles::Access.for(account_user)
  end

  def restricted?
    return false unless @user.is_a?(User)
    return false if account_user.nil? || access.administrator?

    access.restricted_ticket_access?
  end

  def apply(conversations)
    return conversations unless restricted?

    case access.ticket_access
    when 'groups'
      conversations.where('conversations.team_id IN (:teams) OR conversations.assignee_id = :uid OR conversations.id IN (:part)',
                          teams: team_ids_subquery, uid: @user.id, part: participant_subquery)
    when 'assigned'
      conversations.where('conversations.assignee_id = :uid OR conversations.id IN (:part)', uid: @user.id, part: participant_subquery)
    when 'requested'
      conversations.where(contact_id: requester_contact_ids)
    else
      conversations.none
    end
  end

  def allowed?(conversation)
    return true unless restricted?

    case access.ticket_access
    when 'groups' then team_member?(conversation) || own?(conversation)
    when 'assigned' then own?(conversation)
    when 'requested' then requester_contact_ids.include?(conversation.contact_id)
    else false
    end
  end

  # Membros da inbox que podem ver a conversa (para os eventos em tempo real do ActionCable).
  def self.visible_members(conversation)
    members = conversation.inbox.members
    restricted = restricted_account_users(conversation.account_id, members.select(:id))
    return members if restricted.empty?

    denied = restricted.reject { |au| new(au.user, conversation.account, account_user: au).allowed?(conversation) }.map(&:user_id)
    denied.empty? ? members : members.where.not(id: denied)
  end

  def self.restricted_account_users(account_id, user_ids)
    AccountUser.includes(:sd_role, :user).where(account_id: account_id, user_id: user_ids, role: :agent)
               .select { |au| au.sd_access.restricted_ticket_access? }
  end

  private

  def account_user
    @account_user ||= AccountUser.find_by(account_id: @account.id, user_id: @user.id)
  end

  def team_ids_subquery
    TeamMember.joins(:team).where(user_id: @user.id, teams: { account_id: @account.id }).select(:team_id)
  end

  # seguidores (participants) e CCs do ticket (conversation_ccs, pelo e-mail do agente)
  def participant_subquery
    followers = ConversationParticipant.where(user_id: @user.id, account_id: @account.id).select(:conversation_id)
    ccs = ConversationCc.where(account_id: @account.id, email: @user.email.to_s.downcase).select(:conversation_id)
    Conversation.where(account_id: @account.id).where('conversations.id IN (?) OR conversations.id IN (?)', followers, ccs).select(:id)
  end

  def requester_contact_ids
    @requester_contact_ids ||= @account.contacts.where('LOWER(email) = ?', @user.email.to_s.downcase).pluck(:id)
  end

  def team_member?(conversation)
    conversation.team_id.present? && TeamMember.exists?(team_id: conversation.team_id, user_id: @user.id)
  end

  # responsável, seguidor ou em cópia (CC)
  def own?(conversation)
    conversation.assignee_id == @user.id || conversation.conversation_participants.exists?(user_id: @user.id) ||
      ConversationCc.exists?(conversation_id: conversation.id, email: @user.email.to_s.downcase)
  end
end
