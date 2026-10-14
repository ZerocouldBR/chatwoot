class DropLegacyAutomationRules < ActiveRecord::Migration[7.1]
  # The Chatwoot automation engine was replaced by Zendesk-style triggers and automations (ticket_rules).
  def change
    drop_pending_executions
    drop_rules
  end

  private

  def drop_pending_executions
    drop_table :automation_rule_pending_executions do |t|
      t.bigint :automation_rule_id, null: false
      t.bigint :conversation_id, null: false
      t.bigint :account_id, null: false
      t.bigint :message_id
      t.datetime :due_at, null: false
      t.string :episode_key, null: false
      t.integer :status, default: 0, null: false
      t.string :skip_reason
      t.timestamps
      t.index :account_id
      t.index [:automation_rule_id, :conversation_id, :episode_key], name: 'uniq_automation_pending_execution_episode', unique: true
      t.index :automation_rule_id
      t.index :conversation_id
      t.index [:status, :due_at]
      t.index [:status, :updated_at], name: 'index_automation_pending_executions_on_status_and_updated_at'
    end
  end

  def drop_rules
    drop_table :automation_rules do |t|
      t.bigint :account_id, null: false
      t.string :name, null: false
      t.text :description
      t.string :event_name, null: false
      t.jsonb :conditions, default: '{}', null: false
      t.jsonb :actions, default: '{}', null: false
      t.timestamps
      t.boolean :active, default: true, null: false
      t.integer :execution_delay
      t.bigint :monitor_id
      t.datetime :monitor_event_activated_at
      t.index :account_id
      t.index :monitor_id
    end
  end
end
