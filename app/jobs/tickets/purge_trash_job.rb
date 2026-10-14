# Hourly: purges tickets that have been in the trash for longer than the retention period.
class Tickets::PurgeTrashJob < ApplicationJob
  queue_as :scheduled_jobs

  def perform
    Conversation.trashed.where(deleted_at: ...TicketTrashable::TRASH_RETENTION.ago).pluck(:id).each do |id|
      Tickets::PurgeTicketJob.perform_later(id)
    end
  end
end
