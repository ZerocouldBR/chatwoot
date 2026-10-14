# Numbers shown beside the agent home lists: this week's ratings and solved tickets,
# 60-day satisfaction for the agent and the whole support team, open tickets in the
# agent's groups, and recent updates by others on the agent's tickets.
class Tickets::HomeStats
  SATISFACTION_WINDOW = 60.days
  GOOD_RATING = 4
  BAD_RATING = 2
  UPDATES_LIMIT = 10

  pattr_initialize [:account!, :user!]

  def as_json(*)
    {
      week: week_stats,
      satisfaction: { you: satisfaction_rate(ratings.where(assigned_agent_id: user.id)), support: satisfaction_rate(ratings) },
      group_open_tickets: account.conversations.where(status: Conversation::UNSOLVED_STATUSES, team_id: user.teams.where(account: account)).count,
      updates: updates
    }
  end

  private

  def ratings
    account.csat_survey_responses.where(created_at: SATISFACTION_WINDOW.ago..)
  end

  def week_stats
    week = account.csat_survey_responses.where(assigned_agent_id: user.id, created_at: Time.current.beginning_of_week..)
    solved = ConversationEvent.where(account: account, event_type: 'change', field_name: 'status', value: 'resolved', author: user,
                                     created_at: Time.current.beginning_of_week..)
    { good: week.where(rating: GOOD_RATING..).count, bad: week.where(rating: ..BAD_RATING).count, solved: solved.count }
  end

  # Share of good ratings among good and bad ones, as a whole percentage; nil without ratings.
  def satisfaction_rate(scope)
    good = scope.where(rating: GOOD_RATING..).count
    bad = scope.where(rating: ..BAD_RATING).count
    return if (good + bad).zero?

    (good * 100.0 / (good + bad)).round
  end

  def updates
    ticket_ids = account.conversations.where(assignee_id: user.id).or(account.conversations.where(id: ConversationParticipant.where(user_id: user.id)
                                                                                                   .select(:conversation_id))).select(:id)
    ConversationEvent.where(account: account, conversation_id: ticket_ids, event_type: %w[comment change])
                     .where("author_type IS NULL OR NOT (author_type = 'User' AND author_id = ?)", user.id)
                     .includes(:author, :conversation).order(id: :desc).limit(UPDATES_LIMIT).map { |event| update_entry(event) }
  end

  def update_entry(event)
    {
      id: event.id,
      ticket_id: event.conversation.display_id,
      subject: event.conversation.subject,
      event_type: event.event_type,
      field_name: event.field_name,
      author_name: event.author.try(:available_name) || event.author.try(:name),
      created_at: event.created_at.to_i
    }
  end
end
