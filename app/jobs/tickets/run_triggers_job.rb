# Evaluates triggers for a ticket after it changes. Runs are serialised per ticket; a run that finds the ticket busy
# tries again shortly, and events already evaluated are skipped through the ticket's trigger cursor.
class Tickets::RunTriggersJob < ApplicationJob
  queue_as :high

  LOCK_TIMEOUT = 60.seconds
  RETRY_DELAY = 2.seconds

  def perform(conversation_id)
    conversation = Conversation.find_by(id: conversation_id)
    return if conversation.nil?

    ran = Redis::LockManager.new.with_lock("ticket_triggers:#{conversation_id}", LOCK_TIMEOUT) do
      Tickets::Rules::TriggerRunner.new(conversation).perform
    end
    self.class.set(wait: RETRY_DELAY).perform_later(conversation_id) unless ran
  end
end
