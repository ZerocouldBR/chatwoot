# Hourly: runs every active automation, in order, for each account that has them.
class Tickets::RunAutomationsJob < ApplicationJob
  queue_as :scheduled_jobs

  def perform
    TicketRule.kind_automation.active.ordered.each do |automation|
      Tickets::Rules::AutomationRunner.new(automation).perform
    end
  end
end
