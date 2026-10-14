json.id resource.id
# could be nil for a deleted agent hence the safe operator before account id
json.account_id Current.account&.id
json.availability_status resource.availability_status
json.auto_offline resource.auto_offline
json.confirmed resource.confirmed?
json.email resource.email
json.provider resource.provider
json.available_name resource.available_name
json.custom_attributes resource.custom_attributes if resource.custom_attributes.present?
json.name resource.name
json.role resource.role
json.thumbnail resource.avatar_url
# ServiceDesk M13: papel SD do agente na conta atual
sd_account_user = resource.current_account_user
json.sd_role_id sd_account_user&.sd_role_id
json.sd_role_key sd_account_user&.sd_role&.key
json.sd_role_name sd_account_user&.sd_role&.name
json.sd_assignable sd_account_user.nil? || sd_account_user.sd_assignable?
json.ticket_access_override sd_account_user&.ticket_access_override
json.only_private_comments sd_account_user&.only_private_comments || false
json.default_team_id sd_account_user&.default_team_id
json.suspended sd_account_user&.suspended? || false
json.custom_role_id resource.current_account_user&.custom_role_id if ChatwootApp.enterprise?
