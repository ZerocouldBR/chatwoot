# Status changes requested by agents and bots on the ticket endpoints.
module ConversationStatusConcern
  extend ActiveSupport::Concern

  private

  def validate_status_param
    validate_agent_status(params[:status])
  end

  def validate_agent_status(status)
    return if status.blank? || Conversation::AGENT_SETTABLE_STATUSES.include?(status)

    render_could_not_create_error(I18n.t('errors.conversations.invalid_status'))
  end

  def apply_agent_status(status)
    @conversation.status = status
    # Zendesk "assign tickets upon solve": an agent solving an unassigned ticket becomes its assignee.
    @conversation.assignee = Current.user if @conversation.resolved? && @conversation.assignee.blank? && Current.user.is_a?(User)
  end

  def bot_handoff?
    return false unless Current.user.is_a?(AgentBot)

    @conversation.status == 'pending' && params[:status] == 'open'
  end

  def handle_human_open
    @conversation.with_lock do
      @conversation.ai_assignee = nil
      @conversation.assignee = Current.user if Current.user.agent?
      @conversation.save!
    end
  end
end
