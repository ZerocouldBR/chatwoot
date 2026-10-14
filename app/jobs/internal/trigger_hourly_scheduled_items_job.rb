class Internal::TriggerHourlyScheduledItemsJob < ApplicationJob
  queue_as :scheduled_jobs

  def perform
    Channels::Whatsapp::HealthSyncSchedulerJob.perform_later
    Tickets::CloseSolvedTicketsJob.perform_later
    Tickets::RunAutomationsJob.perform_later
    Tickets::PurgeTrashJob.perform_later
    Tickets::PurgeSuspendedTicketsJob.perform_later
  end
end

Internal::TriggerHourlyScheduledItemsJob.prepend_mod_with('Internal::TriggerHourlyScheduledItemsJob')
