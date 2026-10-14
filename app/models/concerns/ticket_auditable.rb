# Records the ticket audit trail (ConversationEvent) for creation and for changes to ticket fields.
module TicketAuditable
  extend ActiveSupport::Concern

  TRIGGER_DELAY = 2.seconds
  AUDITED_FIELDS = %w[
    status priority assignee_id team_id subject ticket_type due_at
    company_id contact_id problem_id satisfaction cached_label_list
  ].freeze

  included do
    has_many :conversation_events, dependent: :delete_all

    after_create_commit :record_create_event
    after_update_commit :record_change_events
  end

  # Who is acting right now and through which path, from the request/job context.
  def self.current_actor
    executed_by = Current.executed_by
    return [executed_by, 'rule'] if executed_by.is_a?(TicketRule)
    return [executed_by, 'customer'] if executed_by.is_a?(Contact)
    return [Current.user, 'agent'] if Current.user.is_a?(User)
    return [Current.user, 'bot'] if Current.user.is_a?(AgentBot)
    return [Current.contact, 'customer'] if Current.contact

    [nil, 'system']
  end

  # details: field_name, previous_value and value.
  def record_ticket_event(event_type:, author:, via:, **details)
    conversation_events.create!(account_id: account_id, event_type: event_type, author: author, via: via, created_at: Time.current,
                                **details.slice(:field_name, :previous_value, :value))
    schedule_triggers
  end

  # Changes made by triggers belong to the update being processed, so only other changes start a trigger run.
  # The short wait lets a ticket and its first message (or a comment and its status change) form one update.
  def schedule_triggers
    return if Current.executed_by.is_a?(TicketRule) && Current.executed_by.kind_trigger?

    Tickets::RunTriggersJob.set(wait: TRIGGER_DELAY).perform_later(id)
  end

  private

  def record_create_event
    author, via = TicketAuditable.current_actor
    record_ticket_event(event_type: 'create', author: author, via: via, value: attributes.slice(*AUDITED_FIELDS).compact)
  end

  def record_change_events
    # nil <-> "" is not a real change (e.g. the label cache being initialised).
    changes = saved_changes.slice(*AUDITED_FIELDS).reject { |_field, values| values.all?(&:blank?) }
    return if changes.empty?

    author, via = TicketAuditable.current_actor
    changes.each do |field, (previous_value, value)|
      record_ticket_event(event_type: 'change', field_name: field, previous_value: previous_value, value: value, author: author, via: via)
    end
  end
end
