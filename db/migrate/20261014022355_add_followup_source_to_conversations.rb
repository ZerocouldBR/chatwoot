class AddFollowupSourceToConversations < ActiveRecord::Migration[7.2]
  disable_ddl_transaction!

  def change
    add_column :conversations, :followup_source_id, :bigint
    add_index :conversations, :followup_source_id, algorithm: :concurrently
    # Used by the hourly job that closes solved tickets.
    add_index :conversations, [:account_id, :status, :status_changed_at], name: 'index_conversations_on_account_status_changed_at',
                                                                          algorithm: :concurrently
  end
end
