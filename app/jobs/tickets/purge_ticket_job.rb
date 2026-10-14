# Deletes a trashed ticket for good. Takes the id because trashed tickets are outside the default scope.
class Tickets::PurgeTicketJob < ApplicationJob
  queue_as :low

  def perform(conversation_id)
    Conversation.trashed.find_by(id: conversation_id)&.destroy!
  end
end
