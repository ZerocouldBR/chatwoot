class AddTeamToMacros < ActiveRecord::Migration[7.1]
  def change
    # Macros available to the agents of one group (Zendesk "Available for: agents in group").
    add_reference :macros, :team, index: true
  end
end
