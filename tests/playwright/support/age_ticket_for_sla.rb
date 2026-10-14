# Test helper: moves a ticket's creation (and its audit trail) back in time and recomputes its SLA.
# ENV: E2E_ACCOUNT_ID, E2E_TICKET_ID (display id), E2E_MINUTES_AGO
account = Account.find(ENV.fetch('E2E_ACCOUNT_ID'))
conversation = account.conversations.find_by!(display_id: ENV.fetch('E2E_TICKET_ID'))
shift = ENV.fetch('E2E_MINUTES_AGO').to_i.minutes
# rubocop:disable Rails/SkipsModelValidations
conversation.update_columns(created_at: conversation.created_at - shift)
conversation.conversation_events.find_each { |event| event.update_columns(created_at: event.created_at - shift) }
# rubocop:enable Rails/SkipsModelValidations
Sla::Applier.new(conversation.reload).perform
puts "E2E_JSON:#{{ sla_breached: conversation.reload.sla_breached }.to_json}"
