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
  # Sessions left over from earlier runs would hit the per-user session limit.
  user.assign_attributes(name: attrs[:name], password: password, password_confirmation: password, tokens: {})
  user.skip_confirmation! if user.new_record?
  user.save!
  AccountUser.find_or_create_by!(account: account, user: user) { |au| au.role = attrs[:role] }
  { id: user.id, email: user.email, name: user.name }
end

api_inbox = account.inboxes.find_by(name: 'E2E API') ||
            account.inboxes.create!(name: 'E2E API', channel: Channel::Api.create!(account: account))
User.where(email: users.values.pluck(:email)).find_each { |u| InboxMember.find_or_create_by!(inbox: api_inbox, user: u) }

# Real e-mail inbox for the e-mail scenarios, when the test mailbox is configured (tests/playwright/.env).
email_inbox_id = nil
if ENV['MAIL_SUPPORT_ADDRESS'].present?
  channel = Channel::Email.find_by(email: ENV.fetch('MAIL_SUPPORT_ADDRESS'), account: account) ||
            Channel::Email.new(account: account, email: ENV.fetch('MAIL_SUPPORT_ADDRESS'))
  channel.update!(
    imap_enabled: true, imap_address: ENV.fetch('MAIL_SUPPORT_IMAP_HOST'), imap_port: ENV.fetch('MAIL_SUPPORT_IMAP_PORT'),
    imap_login: ENV.fetch('MAIL_SUPPORT_USER'), imap_password: ENV.fetch('MAIL_SUPPORT_PASSWORD'), imap_enable_ssl: true,
    smtp_enabled: true, smtp_address: ENV.fetch('MAIL_SUPPORT_SMTP_HOST'), smtp_port: ENV.fetch('MAIL_SUPPORT_SMTP_PORT'),
    smtp_login: ENV.fetch('MAIL_SUPPORT_USER'), smtp_password: ENV.fetch('MAIL_SUPPORT_PASSWORD'), smtp_enable_ssl_tls: true, smtp_enable_starttls_auto: false,
    smtp_domain: ENV.fetch('MAIL_SUPPORT_ADDRESS').split('@').last, smtp_authentication: 'login'
  )
  email_inbox = channel.inbox || account.inboxes.create!(name: 'E2E E-mail', channel: channel)
  User.where(email: users.values.pluck(:email)).find_each { |u| InboxMember.find_or_create_by!(inbox: email_inbox, user: u) }
  email_inbox_id = email_inbox.id
end

# Default triggers and automations, as a new account gets them.
Tickets::Rules::Defaults.new(account).seed

puts "E2E_JSON:#{{ account_id: account.id, users: users, api_inbox_id: api_inbox.id, email_inbox_id: email_inbox_id }.to_json}"
