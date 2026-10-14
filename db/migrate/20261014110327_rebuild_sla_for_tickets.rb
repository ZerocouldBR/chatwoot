# Zendesk-style SLA: ordered policies with conditions and per-priority targets for seven metrics,
# one applied policy per ticket with its computed metric state, and the next breach on the ticket.
class RebuildSlaForTickets < ActiveRecord::Migration[7.2]
  def change
    change_table :sla_policies, bulk: true do |t|
      t.integer :position, null: false, default: 0
      # { "all" => [{ "field" => "priority", "operator" => "equal_to", "values" => ["urgent"] }], "any" => [...] }
      t.jsonb :filter, null: false, default: {}
      # [{ "metric" => "first_reply_time", "priority" => "urgent", "minutes" => 60, "business_hours" => true }]
      t.jsonb :targets, null: false, default: []
      t.remove :first_response_time_threshold, type: :float
      t.remove :next_response_time_threshold, type: :float
      t.remove :resolution_time_threshold, type: :float
      t.remove :only_during_business_hours, type: :boolean, default: false
    end

    change_table :applied_slas, bulk: true do |t|
      # { "first_reply_time" => { "status" => "active", "target_seconds" => 3600, "elapsed_seconds" => 120, "breached" => false } }
      t.jsonb :metrics, null: false, default: {}
      t.datetime :next_breach_at
    end

    add_column :conversations, :next_sla_breach_at, :datetime
    add_column :conversations, :sla_breached, :boolean, null: false, default: false
    add_index :conversations, [:account_id, :next_sla_breach_at]
  end
end
