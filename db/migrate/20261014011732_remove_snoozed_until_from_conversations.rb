class RemoveSnoozedUntilFromConversations < ActiveRecord::Migration[7.2]
  def change
    remove_column :conversations, :snoozed_until, :datetime, precision: nil
  end
end
