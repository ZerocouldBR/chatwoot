# Runs a delayed trigger's actions once its delay is over, if the ticket is not closed and the trigger still matches
# (the ticket as it is now, with the update that matched it).
class Tickets::DelayedTriggerJob < ApplicationJob
  queue_as :medium

  def perform(trigger_id, conversation_id, update)
    trigger = TicketRule.kind_trigger.active.find_by(id: trigger_id)
    conversation = Conversation.find_by(id: conversation_id)
    return if trigger.nil? || conversation.nil? || conversation.closed?
    return unless trigger.matches?(conversation, update: Tickets::Rules::TicketUpdate.new(**update.symbolize_keys))

    deferred = Tickets::Rules::ActionApplier.new(trigger, conversation).perform
    Tickets::Rules::Notifier.new(conversation.reload, deferred).perform if deferred.any?
  end
end
