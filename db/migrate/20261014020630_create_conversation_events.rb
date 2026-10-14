# Append-only ticket audit trail, modelled on Zendesk ticket audit events.
class CreateConversationEvents < ActiveRecord::Migration[7.2]
  def change
    create_table :conversation_events do |t|
      t.bigint :account_id, null: false
      t.bigint :conversation_id, null: false
      t.string :event_type, null: false
      t.string :field_name
      t.jsonb :previous_value
      t.jsonb :value
      t.string :author_type
      t.bigint :author_id
      t.string :via, null: false
      t.datetime :created_at, null: false
    end
    add_index :conversation_events, [:conversation_id, :id]
    add_index :conversation_events, [:account_id, :created_at]
  end
end
