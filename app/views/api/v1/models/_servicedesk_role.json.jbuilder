# ServiceDesk M13: papel e permissões efetivas do usuário na conta (para o painel e o filtro de views por grupo)
access = account_user.sd_access
role = account_user.sd_role
json.role_id role&.id
json.role_key role&.key
json.role_name role&.name
json.base_role account_user.role
json.zendesk_custom_role_id role&.zendesk_custom_role_id&.to_s
json.ticket_access access.ticket_access
json.ticket_access_override account_user.ticket_access_override
json.only_private_comments account_user.only_private_comments
json.default_team_id account_user.default_team_id
json.team_ids account_user.user.teams.where(account_id: account_user.account_id).pluck(:id)
json.permissions access.permissions
