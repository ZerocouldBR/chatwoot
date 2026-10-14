# Hourly: solved tickets become closed once the account's close delay has passed (default 96 hours).
class Tickets::CloseSolvedTicketsJob < ApplicationJob
  queue_as :scheduled_jobs

  def perform
    account_ids = Conversation.resolved.where(status_changed_at: ...1.hour.ago).distinct.pluck(:account_id)
    Account.where(id: account_ids).find_each do |account|
      account.conversations.resolved.where(status_changed_at: ...account.close_solved_after.ago).find_each do |conversation|
        conversation.update!(status: :closed)
      end
    end
  end
end
