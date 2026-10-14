# Deleting a ticket moves it to the trash; it is purged for good after TicketTrashable::TRASH_RETENTION.
class Conversations::DeleteService
  pattr_initialize [:conversation!, :user, :ip]

  def perform
    track_deleted_email_messages
    conversation.trash!
  end

  private

  def track_deleted_email_messages
    return unless conversation.inbox.email?

    Imap::DeletedMessageTracker.new(inbox: conversation.inbox).record(conversation.messages.incoming.pluck(:source_id))
  end
end
