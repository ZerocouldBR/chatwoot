# ServiceDesk M13: guarda a configuration original do papel no Zendesk (custom_roles.json) ao lado das permissões.
class AddZendeskConfigurationToSdRoles < ActiveRecord::Migration[7.1]
  def change
    add_column :sd_roles, :zendesk_configuration, :jsonb, null: false, default: {}
  end
end
