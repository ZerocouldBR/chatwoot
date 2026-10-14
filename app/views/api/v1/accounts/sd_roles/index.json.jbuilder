json.payload do
  json.array! @sd_roles do |sd_role|
    json.partial! 'api/v1/accounts/sd_roles/sd_role', sd_role: sd_role, member_count: @member_counts[sd_role.id].to_i
  end
end
json.catalog do
  json.set! 'keys', (Servicedesk::Roles::Catalog::KEYS.map do |key, type|
    { key: key, type: type == :bool ? 'bool' : 'level', levels: type == :bool ? nil : type }
  end)
  json.pending_keys Servicedesk::Roles::Catalog::PENDING_KEYS
end
