# Removes the isolated E2E account and its users.
# Run with: bundle exec rails runner tests/playwright/support/teardown_e2e_account.rb

account = Account.find_by(name: ENV.fetch('E2E_ACCOUNT_NAME', 'E2E Tickets'))
emails = [ENV.fetch('E2E_ADMIN_EMAIL', 'e2e-admin@helpdesk.test'), ENV.fetch('E2E_AGENT_EMAIL', 'e2e-agent@helpdesk.test')]

DeleteObjectJob.perform_now(account) if account
User.where(email: emails).find_each(&:destroy!)
puts "E2E_JSON:#{{ removed: account.present? }.to_json}"
