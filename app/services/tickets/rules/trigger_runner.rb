# Runs the account's triggers on the update made of the audit events recorded since the last run (Zendesk cycle):
# the first matching trigger fires, then the list is checked again from the top, skipping triggers that already fired,
# until none matches. Changes made by triggers count as part of the update; notifications go out at the end.
# Delayed triggers are scheduled instead of acting right away.
class Tickets::Rules::TriggerRunner
  def initialize(conversation)
    @conversation = conversation
  end

  def perform
    events = new_events
    return if events.empty?

    events, deferred = run_triggers(events) unless @conversation.closed?
    @conversation.update_columns(triggers_event_cursor: events.last.id) # rubocop:disable Rails/SkipsModelValidations
    Tickets::Rules::Notifier.new(@conversation.reload, deferred).perform if deferred.present?
  end

  private

  # Returns the events of the whole update (including the triggers' own changes) and the notifications to send.
  def run_triggers(events)
    triggers = TicketRule.kind_trigger.active.ordered.where(account_id: @conversation.account_id).to_a
    deferred = []
    fired = []
    while (match = next_trigger(triggers - fired, events))
      trigger, update = match
      fired << trigger
      next schedule(trigger, update) if trigger.delay_minutes

      deferred.concat(Tickets::Rules::ActionApplier.new(trigger, @conversation).perform)
      events = new_events
    end
    [events, deferred]
  end

  def next_trigger(triggers, events)
    update = Tickets::Rules::TicketUpdate.from_events(events)
    @conversation.reload
    trigger = triggers.find { |candidate| candidate.matches?(@conversation, update: update) }
    [trigger, update] if trigger
  end

  # A delayed trigger counts as fired for this update; its actions run later if it still matches then.
  def schedule(trigger, update)
    Tickets::DelayedTriggerJob.set(wait: trigger.delay_minutes.minutes).perform_later(trigger.id, @conversation.id, update.to_h)
  end

  def new_events
    scope = @conversation.conversation_events.order(:id)
    scope = scope.where('id > ?', @conversation.triggers_event_cursor) if @conversation.triggers_event_cursor
    scope.to_a
  end
end
