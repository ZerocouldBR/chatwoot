# GET /sc/v2/apps/:app_id/conversations?filter[userId]=sd-contact-<id>: conversas de mensageria do contato.
class ZendeskCompat::Sunshine::ConversationsController < ZendeskCompat::Sunshine::BaseController
  def index
    contact = find_contact!
    conversations = current_account.conversations.where(contact_id: contact.id).joins(:inbox)
                                   .where.not(inboxes: { channel_type: 'Channel::Email' }).order(last_activity_at: :desc).limit(100)
    render json: { conversations: conversations.map { |conversation| conversation_json(conversation) },
                   meta: { hasMore: false, afterCursor: nil, beforeCursor: nil }, links: {} }
  end

  private

  def find_contact!
    user_id = params.dig(:filter, :userId).to_s
    raise ZendeskCompat::Error, 'Use filter[userId]' if user_id.blank?

    contact_id = user_id.delete_prefix('sd-contact-')
    current_account.contacts.find_by(id: ZendeskCompat::Ids.integer(contact_id)) || raise(ZendeskCompat::Error::NotFound, 'User not found')
  end

  def conversation_json(conversation)
    {
      id: conversation.uuid, type: 'personal', displayName: conversation.contact&.name, isDefault: true, activeSwitchboardIntegration: nil,
      lastUpdatedAt: context.time(conversation.last_activity_at || conversation.updated_at),
      metadata: { 'zen:ticket:id' => conversation.display_id, :ticket_id => conversation.display_id }
    }
  end
end
