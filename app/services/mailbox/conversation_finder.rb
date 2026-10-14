class Mailbox::ConversationFinder
  include MailboxSanitizer

  DEFAULT_STRATEGIES = [
    Mailbox::ConversationFinderStrategies::ReceiverUuidStrategy,
    Mailbox::ConversationFinderStrategies::InReplyToStrategy,
    Mailbox::ConversationFinderStrategies::ReferencesStrategy,
    Mailbox::ConversationFinderStrategies::NewConversationStrategy
  ].freeze

  def initialize(mail, strategies: DEFAULT_STRATEGIES)
    @mail = mail
    @strategies = strategies
  end

  def find
    @strategies.each do |strategy_class|
      conversation = strategy_class.new(@mail).find

      next unless conversation

      strategy_name = strategy_class.name.demodulize.underscore
      Rails.logger.info "Conversation found via #{strategy_name} strategy"
      return conversation.persisted? && conversation.closed? ? followup_for(conversation) : conversation
    end

    # Should not reach here if NewConversationStrategy is in the chain
    Rails.logger.error 'No conversation found via any strategy (NewConversationStrategy missing?)'
    nil
  end

  private

  # A reply to a closed ticket opens a linked follow-up ticket (persisted by ReplyMailbox with the message).
  def followup_for(closed_conversation)
    Tickets::FollowupBuilder.new(
      source: closed_conversation,
      additional_attributes: {
        source: 'email',
        in_reply_to: sanitize_mailbox_value(@mail['In-Reply-To'].try(:value)),
        mail_subject: sanitize_mailbox_value(@mail.subject),
        initiated_at: { timestamp: Time.now.utc }
      }
    ).build
  end
end
