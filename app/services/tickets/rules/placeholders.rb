# Renders rule e-mail subjects and bodies with Zendesk-style placeholders ({{ticket.*}}) plus the usual message drops.
module Tickets::Rules::Placeholders
  def self.render(text, conversation)
    drops = {
      'ticket' => TicketDrop.new(conversation),
      'contact' => ContactDrop.new(conversation.contact),
      'conversation' => ConversationDrop.new(conversation),
      'inbox' => InboxDrop.new(conversation.inbox),
      'account' => AccountDrop.new(conversation.account)
    }
    Liquid::Template.parse(text.to_s).render(drops)
  rescue Liquid::Error
    text.to_s
  end
end
