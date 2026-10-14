# Test helper: ages the given solved tickets past the close delay and runs the hourly close job.
# ENV: E2E_ACCOUNT_ID, E2E_TICKET_IDS (comma-separated display ids)
account = Account.find(ENV.fetch('E2E_ACCOUNT_ID'))
ids = ENV.fetch('E2E_TICKET_IDS').split(',')
# rubocop:disable Rails/SkipsModelValidations
account.conversations.where(display_id: ids).resolved.update_all(status_changed_at: (account.close_solved_after + 1.hour).ago)
# rubocop:enable Rails/SkipsModelValidations
Tickets::CloseSolvedTicketsJob.perform_now
puts "E2E_JSON:#{account.conversations.where(display_id: ids).pluck(:display_id, :status).to_h.to_json}"
