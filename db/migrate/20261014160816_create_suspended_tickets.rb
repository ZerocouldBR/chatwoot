class CreateSuspendedTickets < ActiveRecord::Migration[7.1]
  def change
    # E-mails held instead of becoming tickets (Zendesk suspended tickets): recover or delete, purged after 14 days.
    create_table :suspended_tickets do |t|
      t.references :account, null: false, index: false
      t.references :inbox, null: false, index: false
      t.string :from_email, null: false
      t.string :from_name
      t.string :subject
      t.string :message_id
      t.string :reason, null: false
      t.datetime :recovered_at
      t.timestamps
    end
    add_index :suspended_tickets, [:account_id, :created_at]
    add_index :suspended_tickets, [:inbox_id, :message_id]
  end
end
