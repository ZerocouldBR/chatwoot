# Sends the e-mail and webhook actions collected while running ticket rules (Zendesk "Email user", "Email group",
# "Notify active webhook"). Requester e-mails go out through the ticket's channel, threaded with the ticket.
class Tickets::Rules::Notifier
  def initialize(conversation, actions)
    @conversation = conversation
    @account = conversation.account
    @actions = actions
  end

  def perform
    return block_all if Servicedesk::OutboundGuard.blocked?(@account)

    @actions.each do |action|
      action['field'] == 'notify_webhook' ? notify_webhook(action['value']) : email(action['field'], action['value'])
    end
  end

  private

  # ServiceDesk: isolated account. Nothing is e-mailed nor posted; the ticket gets an activity line and an audit event.
  def block_all
    @actions.each do |action|
      field = action['field']
      Servicedesk::OutboundGuard.log("rule #{field}", @account)
      Servicedesk::OutboundGuard.record(@conversation, field, action.slice('rule_id', 'rule_title'))
      @conversation.messages.create!(account_id: @account.id, inbox_id: @conversation.inbox_id, message_type: :activity,
                                     content: blocked_activity(field, action['rule_title']))
    end
  end

  def blocked_activity(field, rule_title)
    I18n.with_locale(Servicedesk::OutboundGuard.locale_for(@account)) do
      next I18n.t('servicedesk.outbound_guard.rule_webhook_not_sent', rule: rule_title) if field == 'notify_webhook'

      I18n.t('servicedesk.outbound_guard.rule_email_not_sent', rule: rule_title,
                                                               recipients: I18n.t("servicedesk.outbound_guard.recipients.#{field}"))
    end
  end

  def email(field, value)
    subject = Tickets::Rules::Placeholders.render(value['subject'], @conversation)
    body = Tickets::Rules::Placeholders.render(value['body'], @conversation)
    if field.start_with?('email_requester')
      ccs = field == 'email_requester_and_ccs' ? @conversation.conversation_ccs.map(&:email) : []
      email_requester(subject, body, cc: ccs)
    else
      email_agents(agents(field, value), subject, body)
    end
  end

  def agents(field, value)
    case field
    when 'email_assignee' then [@conversation.assignee]
    when 'email_group' then group(value['team_id'])&.members.to_a
    else [@account.users.find(value['user_id'])]
    end
  end

  # Without a group in the action, the ticket's group is notified (Zendesk "Email group: (assigned group)").
  def group(team_id)
    team_id.present? ? @account.teams.find(team_id) : @conversation.team
  end

  def email_requester(subject, body, cc:)
    return if @conversation.contact.email.blank? || !@account.within_email_rate_limit?

    TicketRequesterMailer.with(account: @account)
                         .ticket_notification(@conversation, to: @conversation.contact.email, cc: cc, subject: subject, body: body)
                         .deliver_later
    @account.increment_email_sent_count
  end

  def email_agents(users, subject, body)
    emails = users.compact.map(&:email)
    return if emails.empty?

    TicketRuleMailer.with(account: @account).agent_notification(@conversation, emails: emails, subject: subject, body: body).deliver_later
  end

  def notify_webhook(url)
    WebhookJob.perform_later(url, @conversation.webhook_data.merge(event: 'ticket_rule'))
  end
end
