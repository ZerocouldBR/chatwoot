# Evaluates Zendesk-style conditions ({ all: [...], any: [...] }) against a ticket. Shared by triggers, automations
# and SLA policies. Triggers also see the update being processed (Tickets::Rules::TicketUpdate); automations see time.
class Tickets::Rules::Conditions
  ORDERS = {
    'status' => %w[pending new_ticket open waiting_on_customer on_hold resolved closed],
    'priority' => %w[low medium high urgent]
  }.freeze
  CHANGE_OPERATORS = %w[changed changed_to changed_from not_changed].freeze
  IDENTITY_OPERATORS = %w[is is_not].freeze
  FIELD_OPERATORS = {
    'status' => IDENTITY_OPERATORS + %w[less_than greater_than],
    'priority' => IDENTITY_OPERATORS + %w[less_than greater_than],
    'ticket_type' => IDENTITY_OPERATORS,
    'team_id' => IDENTITY_OPERATORS,
    'assignee_id' => IDENTITY_OPERATORS,
    'inbox_id' => IDENTITY_OPERATORS,
    'company_id' => IDENTITY_OPERATORS,
    'contact_id' => IDENTITY_OPERATORS,
    'channel' => IDENTITY_OPERATORS,
    'labels' => %w[includes not_includes],
    'subject' => %w[contains not_contains]
  }.freeze
  CHANGEABLE_FIELDS = %w[status priority ticket_type team_id assignee_id company_id contact_id].freeze
  TRIGGER_OPERATORS = {
    'ticket' => %w[is], # created | updated
    'comment' => %w[is], # public | private | present
    'comment_text' => %w[contains not_contains],
    'update_via' => IDENTITY_OPERATORS, # agent | customer | rule | bot | system
    'within_business_hours' => %w[is] # true | false
  }.freeze
  HOURS_FIELDS = %w[hours_since_created hours_since_updated hours_since_open hours_since_waiting_on_customer hours_since_on_hold
                    hours_since_resolved hours_since_assigned hours_since_requester_update hours_since_assignee_update
                    hours_until_due_date].freeze
  HOURS_OPERATORS = %w[is less_than greater_than].freeze
  SINCE_STATUS = %w[open waiting_on_customer on_hold resolved].freeze

  # kind: trigger, automation or sla.
  def self.fields_for(kind)
    extra = { 'trigger' => TRIGGER_OPERATORS.keys, 'automation' => HOURS_FIELDS }.fetch(kind.to_s, [])
    FIELD_OPERATORS.keys + extra
  end

  def self.operators_for(field, kind)
    return HOURS_OPERATORS if HOURS_FIELDS.include?(field)
    return TRIGGER_OPERATORS.fetch(field) if TRIGGER_OPERATORS.key?(field)

    operators = FIELD_OPERATORS.fetch(field)
    kind.to_s == 'trigger' && CHANGEABLE_FIELDS.include?(field) ? operators + CHANGE_OPERATORS : operators
  end

  def initialize(conditions, conversation, update: nil, now: Time.current)
    @conditions = conditions
    @conversation = conversation
    @update = update
    @now = now
  end

  def match?
    all = @conditions.fetch('all', [])
    any = @conditions.fetch('any', [])
    all.all? { |condition| condition_match?(condition) } && (any.empty? || any.any? { |condition| condition_match?(condition) })
  end

  private

  SPECIAL_FIELDS = %w[channel ticket comment_text update_via within_business_hours].freeze

  def condition_match?(condition)
    field = condition['field']
    operator = condition['operator']
    value = condition['value'].to_s
    return hours_match?(condition) if HOURS_FIELDS.include?(field)
    return comment_kinds.include?(value) if field == 'comment'
    return change_match?(field, operator, value) if CHANGE_OPERATORS.include?(operator)
    return @conversation.label_list.intersect?(value.split) == (operator == 'includes') if field == 'labels'

    compare(field, operator, current(field), value)
  end

  def compare(field, operator, actual, value)
    case operator
    when 'is' then actual == value
    when 'is_not' then actual != value
    when 'contains' then actual.downcase.include?(value.downcase)
    when 'not_contains' then actual.downcase.exclude?(value.downcase)
    when 'less_than' then rank(field, actual) < rank(field, value)
    else rank(field, actual) > rank(field, value)
    end
  end

  def current(field)
    SPECIAL_FIELDS.include?(field) ? send("#{field}_value") : @conversation.public_send(field).to_s
  end

  def channel_value
    @conversation.inbox.channel_type.demodulize.underscore
  end

  def ticket_value
    @update&.created ? 'created' : 'updated'
  end

  def comment_text_value
    @update&.comment_text.to_s
  end

  def update_via_value
    @update&.via.to_s
  end

  def within_business_hours_value
    BusinessSchedule.default_for(@conversation.account)&.open_at?(@now).to_s
  end

  # "comment is public/private/present" checks the comment added in this update.
  def comment_kinds
    comment = @update&.comment
    return [] if comment.nil?

    ['present', comment[:public] ? 'public' : 'private']
  end

  def rank(field, value)
    ORDERS.fetch(field).index(value) || -1
  end

  def change_match?(field, operator, value)
    changes = @update&.changes || {}
    changed = changes.key?(field)
    return !changed if operator == 'not_changed'
    return false unless changed

    from, to = changes[field].map(&:to_s)
    { 'changed' => true, 'changed_to' => to == value, 'changed_from' => from == value }.fetch(operator)
  end

  def hours_match?(condition)
    hours = hours_for(condition['field'], condition['business_hours'])
    return false if hours.nil?

    target = condition['value'].to_i
    case condition['operator']
    when 'is' then hours.floor == target
    when 'less_than' then hours < target
    when 'greater_than' then hours > target
    end
  end

  def hours_for(field, business_hours)
    if field == 'hours_until_due_date'
      return if @conversation.due_at.nil? || @conversation.due_at < @now

      return elapsed(@now, @conversation.due_at, business_hours)
    end

    since = since_time(field.delete_prefix('hours_since_'))
    since && elapsed(since, @now, business_hours)
  end

  def since_time(reference)
    return status_since(reference) if SINCE_STATUS.include?(reference)

    case reference
    when 'created' then @conversation.created_at
    when 'updated' then events.maximum(:created_at)
    when 'assigned' then events.where(field_name: 'assignee_id').where.not(value: nil).maximum(:created_at)
    when 'requester_update' then events.where(event_type: 'comment', via: 'customer').maximum(:created_at)
    when 'assignee_update' then assignee_update_time
    end
  end

  def status_since(status)
    @conversation.status == status ? @conversation.status_changed_at || @conversation.created_at : nil
  end

  def assignee_update_time
    return if @conversation.assignee_id.nil?

    events.where(event_type: 'comment', author_type: 'User', author_id: @conversation.assignee_id).maximum(:created_at)
  end

  def events
    @conversation.conversation_events
  end

  def elapsed(from, to, business_hours)
    seconds = business_hours ? BusinessSchedule.default_for(@conversation.account).elapsed_seconds(from, to) : to - from
    seconds / 3600.0
  end
end
