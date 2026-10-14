# Business hours and holidays (Zendesk "schedules"), used for SLA targets and business-hours rules.
class CreateBusinessSchedules < ActiveRecord::Migration[7.2]
  def change
    create_table :business_schedules do |t|
      t.bigint :account_id, null: false
      t.string :name, null: false
      t.string :time_zone, null: false
      t.boolean :is_default, null: false, default: false
      # [{ "day" => 1, "start" => 540, "end" => 1080 }] — day 0 is Sunday, minutes from midnight.
      t.jsonb :intervals, null: false, default: []
      # [{ "name" => "Natal", "start_date" => "2026-12-25", "end_date" => "2026-12-25" }]
      t.jsonb :holidays, null: false, default: []
      t.timestamps
    end
    add_index :business_schedules, :account_id
    add_index :business_schedules, :account_id, unique: true, where: 'is_default', name: 'index_business_schedules_one_default_per_account'
  end
end
