class Sla::ApplyJob < ApplicationJob
  queue_as :medium

  def perform(conversation_id)
    conversation = Conversation.find_by(id: conversation_id)
    Sla::Applier.new(conversation).perform if conversation
  end
end
