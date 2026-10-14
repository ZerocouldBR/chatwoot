# Applies a ticket rule's actions. Field changes are saved right away (audited with via "rule"); e-mails and webhooks are
# returned so the caller sends them once, with the final ticket state, after every rule of the update has run.
class Tickets::Rules::ActionApplier
  DEFERRED = (TicketRule::EMAIL_ACTIONS + %w[notify_webhook]).freeze

  def initialize(rule, conversation)
    @rule = rule
    @conversation = conversation
  end

  def perform
    Current.executed_by = @rule
    @rule.actions.each_with_object([]) do |action, deferred|
      next deferred << action if DEFERRED.include?(action['field'])

      apply(action['field'], action['value'])
    end
  ensure
    Current.executed_by = nil
  end

  private

  def apply(field, value)
    case field
    when 'status', 'priority', 'ticket_type' then @conversation.update!(field => value)
    when 'team_id', 'assignee_id' then @conversation.update!(field => value.presence)
    when 'add_tags', 'remove_tags', 'set_tags' then @conversation.update!(label_list: new_tags(field, value.to_s.split))
    else act(field, value)
    end
  end

  def act(field, value)
    case field
    when 'add_cc' then Tickets::CcList.new(@conversation).add(value, author: @rule, via: 'rule')
    when 'add_follower' then @conversation.conversation_participants.find_or_create_by!(user_id: value)
    when 'request_satisfaction' then Tickets::SatisfactionRequestService.new(conversation: @conversation).perform
    when 'send_message' then send_message(value)
    end
  end

  # A public reply through the ticket's channel (chat message or e-mail), with Liquid placeholders like {{ticket.id}}.
  def send_message(content)
    Messages::MessageBuilder.new(nil, @conversation, { content: content, private: false, content_attributes: { ticket_rule_id: @rule.id } })
                            .perform
  end

  def new_tags(field, tags)
    { 'add_tags' => @conversation.label_list | tags, 'remove_tags' => @conversation.label_list - tags, 'set_tags' => tags }.fetch(field)
  end
end
