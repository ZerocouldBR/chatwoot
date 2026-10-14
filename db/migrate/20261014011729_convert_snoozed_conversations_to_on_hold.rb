# Tickets have no "snoozed" status: snoozed conversations become On-hold (status 6),
# and saved filters / automation conditions that referenced "snoozed" now reference "on_hold".
class ConvertSnoozedConversationsToOnHold < ActiveRecord::Migration[7.2]
  def up
    execute 'UPDATE conversations SET status = 6 WHERE status = 3'
    execute "UPDATE custom_filters SET query = replace(query::text, '\"snoozed\"', '\"on_hold\"')::jsonb WHERE query::text LIKE '%\"snoozed\"%'"
    execute "UPDATE automation_rules SET conditions = replace(conditions::text, '\"snoozed\"', '\"on_hold\"')::jsonb " \
            "WHERE conditions::text LIKE '%\"snoozed\"%'"
  end

  def down
    raise ActiveRecord::IrreversibleMigration
  end
end
