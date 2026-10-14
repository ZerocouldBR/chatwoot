# Computes the state of every SLA metric of a ticket from its audit trail (ConversationEvent),
# following Zendesk's SLA rules:
# - first reply time: creation until the first public agent reply (or until solved);
# - next reply time: each customer public comment after an agent reply until the next agent reply;
# - periodic update: gaps between public agent replies; pausable update: the same, paused while Pending;
# - requester wait time: paused while Pending; agent work time: paused while Pending and On-hold;
# - total resolution time: creation until solved, never paused.
# Solved/closed tickets stop every metric; reopening resumes the time-based ones.
class Sla::Calculator
  SOLVED = %w[resolved closed].freeze
  # The bot state (`pending`) is excluded from SLA, like Zendesk's AI agent tickets.
  NOT_MEASURED = (SOLVED + %w[pending]).freeze
  PAUSES = {
    'pausable_update' => %w[waiting_on_customer],
    'requester_wait_time' => %w[waiting_on_customer],
    'agent_work_time' => %w[waiting_on_customer on_hold]
  }.freeze
  COMMENT_KINDS = { 'customer' => :customer, 'agent' => :agent, 'bot' => :agent }.freeze

  pattr_initialize [:conversation!, :policy!, :schedule, :now!]

  def metrics
    SlaPolicy::METRICS.filter_map do |metric|
      target = policy.target_for(metric, conversation.priority)
      [metric, measure(metric, target)] if target
    end.to_h
  end

  private

  def measure(metric, target)
    instance = send("#{metric}_instance")
    return { 'status' => 'not_started', 'target_seconds' => target['minutes'] * 60 } if instance.nil?

    build_state(metric, target, *instance)
  end

  # Each *_instance returns [start, stop, earlier] for the instance that decides the metric state:
  # stop is nil while it is still running; earlier lists the finished [start, stop] instances before it.
  def first_reply_time_instance
    stop = [first_agent_reply_at, first_solved_at].compact.min
    [created_at, stop, []]
  end

  def next_reply_time_instance
    instances = []
    open_since = nil
    comments_after_first_reply.each do |time, kind|
      if kind == :customer
        open_since ||= time
      elsif open_since
        instances << [open_since, time]
        open_since = nil
      end
    end
    last_instance(instances, open_since)
  end

  def periodic_update_instance
    replies = comments.select { |_time, kind| kind == :agent }.map(&:first)
    return if replies.empty?

    instances = replies.each_cons(2).to_a
    last_instance(instances, replies.last)
  end
  alias pausable_update_instance periodic_update_instance

  def requester_wait_time_instance
    [created_at, solved? ? status_changed_at : nil, []]
  end
  alias agent_work_time_instance requester_wait_time_instance
  alias total_resolution_time_instance requester_wait_time_instance

  def last_instance(finished, running_since)
    previous = finished.to_a
    return [running_since, solved? ? status_changed_at : nil, previous] if running_since
    return if previous.empty?

    *earlier, (start, stop) = previous
    [start, stop, earlier]
  end

  def build_state(metric, target, start, stop, earlier)
    target_seconds = target['minutes'] * 60
    business = target['business_hours']
    elapsed = elapsed_seconds(metric, start, stop || now, business)
    breached = elapsed > target_seconds || earlier_breach?(metric, earlier, target_seconds, business)
    state = { 'target_seconds' => target_seconds, 'business_hours' => business, 'elapsed_seconds' => elapsed, 'breached' => breached }
    return state.merge('status' => 'fulfilled', 'fulfilled_at' => stop.iso8601) if stop
    return state.merge('status' => 'paused') if paused?(metric)

    breach_at = breached ? nil : advance(now, target_seconds - elapsed, business)
    state.merge('status' => 'active', 'breach_at' => breach_at&.iso8601)
  end

  def earlier_breach?(metric, earlier, target_seconds, business)
    earlier.any? { |from, to| elapsed_seconds(metric, from, to, business) > target_seconds }
  end

  # Time counted for a metric between two instants: only while the ticket is measured and not paused.
  def elapsed_seconds(metric, from, to, business)
    excluded = NOT_MEASURED + PAUSES.fetch(metric, [])
    running_ranges(from, to, excluded).sum do |range_start, range_end|
      business ? schedule.elapsed_seconds(range_start, range_end) : (range_end - range_start).to_i
    end
  end

  def running_ranges(from, to, excluded)
    status_timeline.each_cons(2).filter_map do |(start, status), (finish, _next)|
      next if excluded.include?(status)

      range_start = [start, from].max
      range_end = [finish, to].min
      [range_start, range_end] if range_end > range_start
    end
  end

  def advance(from, seconds, business)
    business ? schedule.add_seconds(from, seconds) : from + seconds
  end

  def paused?(metric)
    PAUSES.fetch(metric, []).include?(conversation.status)
  end

  def solved?
    SOLVED.include?(conversation.status)
  end

  def created_at
    conversation.created_at
  end

  def status_changed_at
    conversation.status_changed_at || now
  end

  # [[time, status], ...] ending with a sentinel at `now`.
  def status_timeline
    @status_timeline ||= begin
      changes = events.select { |event| event.event_type == 'change' && event.field_name == 'status' }
      initial = changes.first&.previous_value || conversation.status
      [[created_at, initial]] + changes.map { |event| [event.created_at, event.value] } + [[now, nil]]
    end
  end

  # [[time, :customer | :agent], ...] for public comments.
  def comments
    @comments ||= events.select { |event| event.event_type == 'comment' && event.value&.dig('public') }.filter_map do |event|
      kind = COMMENT_KINDS[event.via]
      [event.created_at, kind] if kind
    end
  end

  def comments_after_first_reply
    return [] unless first_agent_reply_at

    comments.select { |time, _kind| time > first_agent_reply_at }
  end

  def first_agent_reply_at
    comments.find { |_time, kind| kind == :agent }&.first
  end

  def first_solved_at
    status_timeline.find { |_time, status| SOLVED.include?(status) }&.first
  end

  def events
    @events ||= conversation.conversation_events.where(event_type: %w[change comment]).order(:id).to_a
  end
end
