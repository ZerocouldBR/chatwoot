# After a policy changes, every unsolved ticket of the account is matched again.
class Sla::ReapplyAccountJob < ApplicationJob
  queue_as :low

  def perform(account_id)
    Conversation.where(account_id: account_id, status: Conversation::UNSOLVED_STATUSES).find_each do |conversation|
      Sla::Applier.new(conversation).perform
    end
  end
end
