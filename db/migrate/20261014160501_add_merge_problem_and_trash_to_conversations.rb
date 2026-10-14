class AddMergeProblemAndTrashToConversations < ActiveRecord::Migration[7.1]
  def change
    # Ticket this one was merged into (Zendesk closes the source ticket of a merge).
    add_column :conversations, :merged_into_id, :bigint
    # Problem ticket an incident is linked to.
    add_column :conversations, :problem_id, :bigint
    add_index :conversations, :problem_id
    # Deleted tickets stay in the trash for 30 days before being purged.
    add_column :conversations, :deleted_at, :datetime
    add_index :conversations, [:account_id, :deleted_at]
  end
end
