# One ticket update as triggers see it, built from the audit events recorded since the last trigger run:
# whether the ticket was created, which fields changed (first previous value -> last value), the comment added and who acted.
class Tickets::Rules::TicketUpdate
  attr_reader :created, :changes, :comment, :comment_text, :via

  def initialize(events)
    @created = events.any? { |event| event.event_type == 'create' }
    @changes = build_changes(events)
    comment_event = events.reverse.find { |event| event.event_type == 'comment' }
    @comment = comment_event && { public: comment_event.value['public'] }
    @comment_text = comment_event && Message.find_by(id: comment_event.value['message_id'])&.content
    @via = acting_event(events, comment_event).via
  end

  private

  # Who made the update: the comment author when there is one (a new e-mail ticket is created by the system and
  # commented by the customer), otherwise whoever changed the ticket first.
  def acting_event(events, comment_event)
    comment_event || events.find { |event| event.via != 'rule' } || events.first
  end

  def build_changes(events)
    events.select { |event| event.event_type == 'change' }.group_by(&:field_name).transform_values do |field_events|
      [field_events.first.previous_value, field_events.last.value]
    end
  end
end
