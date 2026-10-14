# Hourly: deletes suspended e-mails older than the retention period.
class Tickets::PurgeSuspendedTicketsJob < ApplicationJob
  queue_as :scheduled_jobs

  def perform
    SuspendedTicket.where(created_at: ...SuspendedTicket::RETENTION.ago).find_each(&:destroy!)
  end
end
