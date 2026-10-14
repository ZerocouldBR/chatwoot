# ServiceDesk M13: papéis por conta (sd_roles) e vínculo do account_user com o papel.
# Não reutiliza custom_roles/custom_role_id (enterprise). Reversível. Sem foreign keys (padrão do repo: associações).
class CreateSdRoles < ActiveRecord::Migration[7.1]
  def change
    create_sd_roles
    add_account_user_role_columns
  end

  private

  def create_sd_roles
    create_table :sd_roles do |t|
      t.references :account, null: false, index: true
      t.string :key, null: false
      t.string :name, null: false
      t.text :description
      t.integer :base_role, null: false, default: 0
      t.jsonb :permissions, null: false, default: {}
      t.bigint :zendesk_custom_role_id
      t.boolean :system, null: false, default: false
      t.integer :position, null: false, default: 0
      t.timestamps
    end
    add_index :sd_roles, [:account_id, :key], unique: true
    add_index :sd_roles, [:account_id, :name], unique: true
  end

  def add_account_user_role_columns
    change_table :account_users, bulk: true do |t|
      t.references :sd_role, null: true, index: true
      t.string :ticket_access_override
      t.boolean :only_private_comments, null: false, default: false
      t.bigint :default_team_id
      t.datetime :suspended_at
      t.bigint :zendesk_user_id
    end
    add_index :account_users, :zendesk_user_id
  end
end
