# Runs the account's triggers on the update made of the audit events recorded since the last run (Zendesk cycle):
# the first matching trigger fires, then the list is checked again from the top, skipping triggers that already fired,
# until none matches. Changes made by triggers count as part of the update; notifications go out at the end.
class Tickets::Rules::TriggerRunner
  def initialize(conversation)
    @conversation = conversation
  end

  def perform
    events = new_events
    return if events.empty?

    deferred = []
    fired = []
    unless @conversation.closed?
      triggers = TicketRule.kind_trigger.active.ordered.where(account_id: @conversation.account_id).to_a
      while (trigger = next_trigger(triggers - fired, events))
        fired << trigger
        deferred.concat(Tickets::Rules::ActionApplier.new(trigger, @conversation).perform)
        events = new_events
      end
    end
    @conversation.update_columns(triggers_event_cursor: events.last.id) # rubocop:disable Rails/SkipsModelValidations
    Tickets::Rules::Notifier.new(@conversation.reload, deferred).perform if deferred.any?
  end

  private

  def next_trigger(triggers, events)
    update = Tickets::Rules::TicketUpdate.new(events)
    @conversation.reload
    triggers.find { |trigger| trigger.matches?(@conversation, update: update) }
  end

  def new_events
    scope = @conversation.conversation_events.order(:id)
    scope = scope.where('id > ?', @conversation.triggers_event_cursor) if @conversation.triggers_event_cursor
    scope.to_a
  end
end
