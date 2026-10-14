# Every minute: tickets whose next SLA target just passed are recomputed so the breach is recorded.
class Sla::ProcessBreachesJob < ApplicationJob
  queue_as :scheduled_jobs

  def perform
    Conversation.where(next_sla_breach_at: ..Time.current).where.not(status: :closed).find_each do |conversation|
      Sla::Applier.new(conversation).perform
    end
  end
end
