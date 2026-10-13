# Idempotently prepares an isolated account for the ticket E2E suite.
# Run with: bundle exec rails runner tests/playwright/support/setup_e2e_account.rb
# Prints a single "E2E_JSON:{...}" line consumed by helpers/rails.ts.

account_name = ENV.fetch('E2E_ACCOUNT_NAME', 'E2E Tickets')
password = ENV.fetch('E2E_PASSWORD')

account = Account.find_or_create_by!(name: account_name) { |a| a.locale = 'pt_BR' }

users = {
  admin: { email: ENV.fetch('E2E_ADMIN_EMAIL', 'e2e-admin@helpdesk.test'), name: 'Ana Admin', role: :administrator },
  agent: { email: ENV.fetch('E2E_AGENT_EMAIL', 'e2e-agent@helpdesk.test'), name: 'Bruno Agente', role: :agent }
}.transform_values do |attrs|
  user = User.find_or_initialize_by(email: attrs[:email])
  user.assign_attributes(name: attrs[:name], password: password, password_confirmation: password)
  user.skip_confirmation! if user.new_record?
  user.save!
  AccountUser.find_or_create_by!(account: account, user: user) { |au| au.role = attrs[:role] }
  { id: user.id, email: user.email, name: user.name }
end

api_inbox = account.inboxes.find_by(name: 'E2E API') ||
            account.inboxes.create!(name: 'E2E API', channel: Channel::Api.create!(account: account))
User.where(email: users.values.pluck(:email)).find_each { |u| InboxMember.find_or_create_by!(inbox: api_inbox, user: u) }

puts "E2E_JSON:#{{ account_id: account.id, users: users, api_inbox_id: api_inbox.id }.to_json}"
