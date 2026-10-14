class AddDelayMinutesToTicketRules < ActiveRecord::Migration[7.1]
  def change
    # A trigger can act some minutes after the update that matched it, if it still matches then.
    add_column :ticket_rules, :delay_minutes, :integer
  end
end
