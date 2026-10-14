# The agent home page lists, like Zendesk's home: your unsolved tickets, tickets you are
# CC'd on or following, and what you solved in the last 30 days.
class Tickets::HomeQuery
  VIEWS = %w[mine ccs following solved].freeze
  PER_PAGE = 25
  SOLVED_WINDOW = 30.days

  pattr_initialize [:account!, :user!]

  def tickets(view, page: 1)
    scope_for(view).includes(:contact, :inbox, :team, :assignee, :conversation_ccs)
                   .order(last_activity_at: :desc).page(page).per(PER_PAGE)
  end

  def counts
    VIEWS.index_with { |view| scope_for(view).count }
  end

  private

  def scope_for(view)
    case view
    when 'mine' then accessible.where(assignee_id: user.id, status: Conversation::UNSOLVED_STATUSES)
    when 'ccs' then accessible.where(status: Conversation::UNSOLVED_STATUSES).where(id: ConversationCc.where(email: user.email.downcase)
                                                                                                  .select(:conversation_id))
    when 'following'
      accessible.where(status: Conversation::UNSOLVED_STATUSES).where(id: ConversationParticipant.where(user_id: user.id).select(:conversation_id))
    when 'solved'
      accessible.where(assignee_id: user.id, status: %w[resolved closed]).where(status_changed_at: SOLVED_WINDOW.ago..)
    end
  end

  def accessible
    Conversations::PermissionFilterService.new(account.conversations, user, account).perform
  end
end
