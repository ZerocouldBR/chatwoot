namespace :tickets do
  desc 'Create the default triggers and automations for accounts that have none'
  task seed_default_rules: :environment do
    Account.find_each { |account| Tickets::Rules::Defaults.new(account).seed }
  end
end
