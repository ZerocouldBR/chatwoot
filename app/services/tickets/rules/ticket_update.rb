# One ticket update as triggers see it, built from the audit events recorded since the last trigger run:
# whether the ticket was created, which fields changed (first previous value -> last value), the comment added and who acted.
# It can be serialized so a delayed trigger re-checks its conditions against the update that matched it.
class Tickets::Rules::TicketUpdate
  attr_reader :created, :changes, :comment, :comment_text, :via

  def self.from_events(events)
    comment_event = events.reverse.find { |event| event.event_type == 'comment' }
    new(created: events.any? { |event| event.event_type == 'create' }, changes: changes_from(events),
        **comment_details(comment_event), via: acting_event(events, comment_event).via)
  end

  def self.comment_details(event)
    return { comment: nil, comment_text: nil } if event.nil?

    { comment: { public: event.value['public'] }, comment_text: Message.find_by(id: event.value['message_id'])&.content }
  end

  # Who made the update: the comment author when there is one (a new e-mail ticket is created by the system and
  # commented by the customer), otherwise whoever changed the ticket first.
  def self.acting_event(events, comment_event)
    comment_event || events.find { |event| event.via != 'rule' } || events.first
  end

  def self.changes_from(events)
    events.select { |event| event.event_type == 'change' }.group_by(&:field_name).transform_values do |field_events|
      [field_events.first.previous_value, field_events.last.value]
    end
  end
  private_class_method :changes_from, :comment_details, :acting_event

  def initialize(created:, changes:, comment:, comment_text:, via:)
    @created = created
    @changes = changes
    @comment = comment&.symbolize_keys
    @comment_text = comment_text
    @via = via
  end

  def to_h
    { created: created, changes: changes, comment: comment, comment_text: comment_text, via: via }
  end
end
