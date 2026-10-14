class AddTicketFieldsToConversations < ActiveRecord::Migration[7.2]
  def change
    change_table :conversations, bulk: true do |t|
      t.string :subject, limit: 150
      t.integer :ticket_type
      t.datetime :due_at
      t.bigint :submitter_id
      t.bigint :company_id
    end
    add_index :conversations, [:account_id, :due_at]
    add_index :conversations, :company_id
  end
end
