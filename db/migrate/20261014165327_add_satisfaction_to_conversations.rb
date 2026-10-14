class AddSatisfactionToConversations < ActiveRecord::Migration[7.1]
  def change
    # Zendesk satisfaction: unoffered, offered, good or bad.
    add_column :conversations, :satisfaction, :integer, null: false, default: 0
  end
end
