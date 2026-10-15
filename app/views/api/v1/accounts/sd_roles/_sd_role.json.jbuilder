json.id sd_role.id
json.key sd_role.key
json.name sd_role.name
json.description sd_role.description
json.base_role sd_role.base_role
json.system sd_role.system
json.position sd_role.position
json.zendesk_custom_role_id sd_role.zendesk_custom_role_id&.to_s
json.permissions sd_role.effective_permissions
json.zendesk_configuration sd_role.zendesk_configuration
json.members_count member_count unless member_count.nil?
