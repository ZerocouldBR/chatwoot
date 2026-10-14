# The default triggers and automations every account starts with, like Zendesk's (editable afterwards).
# Agent notifications (new ticket, assignment, mentions) stay with the notification settings of each agent,
# and replies are e-mailed by the channel itself, so those Zendesk defaults have no trigger here.
class Tickets::Rules::Defaults
  def initialize(account)
    @account = account
  end

  def seed
    return if TicketRule.exists?(account: @account)

    I18n.with_locale(@account.locale.presence || I18n.default_locale) do
      triggers.each.with_index(1) { |attributes, position| create(:trigger, position, attributes) }
      automations.each.with_index(1) { |attributes, position| create(:automation, position, attributes) }
    end
  end

  private

  def create(kind, position, attributes)
    TicketRule.create!(account: @account, kind: kind, position: position, **attributes)
  end

  def triggers
    [
      { title: t('request_received.title'),
        conditions: { all: [condition('ticket', 'is', 'created'), condition('update_via', 'is', 'customer')], any: [] },
        actions: [email('email_requester_and_ccs', 'request_received')] },
      { title: t('default_priority.title'),
        conditions: { all: [condition('ticket', 'is', 'created'), condition('priority', 'is', '')], any: [] },
        actions: [{ field: 'priority', value: 'medium' }] },
      { title: t('group_assignment.title'),
        conditions: { all: [condition('team_id', 'changed'), condition('team_id', 'is_not', ''), condition('assignee_id', 'is', '')], any: [] },
        actions: [{ field: 'email_group', value: email_value('group_assignment').merge(team_id: '') }] }
    ]
  end

  def automations
    [
      pending_reminder('pending_reminder_24h', 24),
      pending_reminder('pending_reminder_5d', 120),
      satisfaction_request
    ]
  end

  # Zendesk's system automation: one day after the ticket is solved, the requester is asked to rate it.
  def satisfaction_request
    { title: t('satisfaction_request.title'), active: false,
      conditions: { all: [condition('status', 'is', 'resolved'), condition('hours_since_resolved', 'is', '24'),
                          condition('satisfaction', 'is', 'unoffered')], any: [] },
      actions: [{ field: 'request_satisfaction', value: '' }] }
  end

  def pending_reminder(key, hours)
    { title: t("#{key}.title"), active: false,
      conditions: { all: [condition('status', 'is', 'waiting_on_customer'), condition('hours_since_waiting_on_customer', 'is', hours.to_s)],
                    any: [] },
      actions: [email('email_requester_and_ccs', key)] }
  end

  def condition(field, operator, value = nil)
    { field: field, operator: operator, value: value }
  end

  def email(field, key)
    { field: field, value: email_value(key) }
  end

  def email_value(key)
    { subject: t("#{key}.subject"), body: t("#{key}.body") }
  end

  def t(key)
    I18n.t("tickets.rules.defaults.#{key}")
  end
end
