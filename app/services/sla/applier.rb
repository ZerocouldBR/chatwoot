# Applies the first matching SLA policy to a ticket and stores the computed metric state,
# the next breach (for badges and sorting) and breach/fulfil events.
class Sla::Applier
  pattr_initialize :conversation

  def perform(now: Time.current)
    return if conversation.closed?

    policy = matching_policy
    return remove_sla if policy.nil?

    applied = applied_for(policy)
    previous = applied.metrics
    metrics = Sla::Calculator.new(conversation: conversation, policy: policy, schedule: BusinessSchedule.default_for(conversation.account),
                                  now: now).metrics
    record_events(applied, previous, metrics)
    store(applied, policy, metrics)
  end

  private

  def matching_policy
    return if conversation.priority.nil? || conversation.pending?

    SlaPolicy.where(account_id: conversation.account_id).ordered.find { |policy| policy.matches?(conversation) }
  end

  def applied_for(policy)
    current = AppliedSla.find_by(conversation: conversation)
    return current if current&.sla_policy_id == policy.id

    current&.destroy!
    AppliedSla.create!(account_id: conversation.account_id, conversation: conversation, sla_policy: policy)
  end

  def record_events(applied, previous, metrics)
    metrics.each do |metric, state|
      before = previous[metric] || {}
      create_event(applied, :breach, metric) if state['breached'] && !before['breached']
      create_event(applied, :fulfill, metric) if state['status'] == 'fulfilled' && before['status'] != 'fulfilled'
    end
  end

  # Breached reply and resolution targets notify the assignee (Zendesk does this through SLA triggers).
  BREACH_NOTIFICATIONS = {
    'first_reply_time' => 'sla_missed_first_response',
    'next_reply_time' => 'sla_missed_next_response',
    'total_resolution_time' => 'sla_missed_resolution'
  }.freeze

  def create_event(applied, type, metric)
    SlaEvent.create!(account_id: conversation.account_id, applied_sla: applied, conversation: conversation, sla_policy: applied.sla_policy,
                     inbox_id: conversation.inbox_id, event_type: type, meta: { metric: metric })
    notify_breach(metric) if type == :breach
  end

  def notify_breach(metric)
    notification_type = BREACH_NOTIFICATIONS[metric]
    return if notification_type.nil? || conversation.assignee.nil?

    NotificationBuilder.new(notification_type: notification_type, user: conversation.assignee, account: conversation.account,
                            primary_actor: conversation).perform
  end

  def store(applied, policy, metrics)
    states = metrics.values
    next_breach_at = states.filter_map { |state| state['breach_at'] }.min
    breached = states.any? { |state| state['breached'] }
    applied.update!(metrics: metrics, next_breach_at: next_breach_at, sla_status: overall_status(states, breached))
    update_conversation(sla_policy_id: policy.id, next_sla_breach_at: next_breach_at, sla_breached: breached)
  end

  def overall_status(states, breached)
    return :missed if breached
    return :hit if states.all? { |state| state['status'] == 'fulfilled' }

    :active
  end

  def remove_sla
    AppliedSla.where(conversation: conversation).destroy_all
    update_conversation(sla_policy_id: nil, next_sla_breach_at: nil, sla_breached: false)
  end

  # Written without callbacks (this runs from them) and pushed to agents as a regular ticket update.
  def update_conversation(attributes)
    return if attributes.all? { |key, value| conversation.public_send(key) == value }

    conversation.update_columns(attributes) # rubocop:disable Rails/SkipsModelValidations
    conversation.dispatch_conversation_updated_event
  end
end
