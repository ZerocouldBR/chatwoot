# Ticket CCs (Zendesk "CCs"): people copied on every public reply of a ticket.
class CreateConversationCcs < ActiveRecord::Migration[7.2]
  def change
    create_table :conversation_ccs do |t|
      t.bigint :account_id, null: false
      t.bigint :conversation_id, null: false
      t.string :email, null: false
      t.timestamps
    end
    add_index :conversation_ccs, [:conversation_id, :email], unique: true
    add_index :conversation_ccs, [:account_id, :email]
  end
end
