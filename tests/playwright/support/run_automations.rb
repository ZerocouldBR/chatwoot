# Test helper: moves the given tickets' last status change back in time and runs this account's automations
# (only this account's, so other accounts on a shared server are untouched).
# ENV: E2E_ACCOUNT_ID, E2E_TICKET_IDS (comma-separated display ids), E2E_HOURS_AGO
account = Account.find(ENV.fetch('E2E_ACCOUNT_ID'))
tickets = account.conversations.where(display_id: ENV.fetch('E2E_TICKET_IDS').split(','))
tickets.update_all(status_changed_at: ENV.fetch('E2E_HOURS_AGO').to_i.hours.ago) # rubocop:disable Rails/SkipsModelValidations
TicketRule.kind_automation.active.ordered.where(account: account).each { |automation| Tickets::Rules::AutomationRunner.new(automation).perform }
puts "E2E_JSON:#{tickets.reload.to_h { |ticket| [ticket.display_id, { status: ticket.status, labels: ticket.label_list }] }.to_json}"
