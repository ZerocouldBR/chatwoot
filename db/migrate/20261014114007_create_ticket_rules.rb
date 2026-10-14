class CreateTicketRules < ActiveRecord::Migration[7.1]
  def change
    # Zendesk triggers (run on every ticket update, in order) and automations (run hourly on time conditions).
    create_table :ticket_rules do |t|
      t.references :account, null: false, index: true
      t.integer :kind, null: false
      t.string :title, null: false
      t.string :description
      t.boolean :active, null: false, default: true
      t.integer :position, null: false, default: 0
      t.jsonb :conditions, null: false, default: { all: [], any: [] }
      t.jsonb :actions, null: false, default: []
      t.timestamps
    end
    add_index :ticket_rules, [:account_id, :kind, :position]

    # Last audit event already evaluated by triggers: the events after it form the next ticket update.
    add_column :conversations, :triggers_event_cursor, :bigint

    reversible { |dir| dir.up { convert_sla_conditions } }
  end

  private

  # SLA conditions now share the trigger condition format: a single `value` and the trigger operator names.
  def convert_sla_conditions
    condition = <<~SQL.squish
      jsonb_build_object('field', c->>'field', 'value', c->'values'->>0, 'operator',
        CASE WHEN c->>'field' = 'labels' THEN (CASE c->>'operator' WHEN 'equal_to' THEN 'includes' ELSE 'not_includes' END)
             ELSE (CASE c->>'operator' WHEN 'equal_to' THEN 'is' ELSE 'is_not' END) END)
    SQL
    execute <<~SQL.squish
      UPDATE sla_policies SET filter = jsonb_build_object(
        'all', COALESCE((SELECT jsonb_agg(#{condition}) FROM jsonb_array_elements(filter->'all') c), '[]'::jsonb),
        'any', COALESCE((SELECT jsonb_agg(#{condition}) FROM jsonb_array_elements(filter->'any') c), '[]'::jsonb))
      WHERE filter <> '{}'::jsonb
    SQL
  end
end
