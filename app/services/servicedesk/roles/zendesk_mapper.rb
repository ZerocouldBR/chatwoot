# ServiceDesk M13: converte a configuration de um papel do Zendesk (GET /api/v2/custom_roles) nas permissões do
# ServiceDesk, chave a chave. Usado pelo provision_roles.rb para gravar os papéis exatamente como no Zendesk.
module Servicedesk::Roles::ZendeskMapper
  TICKET_ACCESS = { 'all' => 'all', 'within-groups' => 'groups', 'within-groups-and-public-groups' => 'groups',
                    'assigned-only' => 'assigned', 'within-organization' => 'requested' }.freeze
  MANAGE_LEVEL = { 'full' => 'full', 'manage-personal' => 'personal', 'manage-group' => 'personal',
                   'readonly' => 'readonly', 'playonly' => 'readonly' }.freeze
  LEVELS3 = %w[none readonly full].freeze

  module_function

  def permissions(config)
    cfg = config.to_h.stringify_keys
    ticket_permissions(cfg).merge(people_permissions(cfg)).merge(tool_permissions(cfg))
  end

  def ticket_permissions(cfg)
    { 'ticket.access' => TICKET_ACCESS.fetch(cfg['ticket_access'].to_s, 'assigned'),
      'ticket.comment_public' => cfg['ticket_comment_access'] == 'public' && !cfg['light_agent'],
      'ticket.edit' => cfg['ticket_editing'] == true, 'ticket.edit_tags' => cfg['ticket_tag_editing'] == true,
      'ticket.assignable' => !cfg['light_agent'] && cfg['ticket_comment_access'] != 'none',
      'ticket.assign_any_team' => cfg['assign_tickets_to_any_group'] == true, 'ticket.merge' => cfg['ticket_merge'] == true,
      'ticket.delete' => cfg['ticket_deletion'] == true, 'ticket.redact' => cfg['ticket_redaction'] == true,
      'ticket.modify_closed' => cfg['modify_closed_tickets'] == true, 'ticket.view_deleted' => cfg['view_deleted_tickets'] == true,
      'suspended_tickets.manage' => cfg['manage_suspended_tickets'] == true,
      'side_conversations' => cfg['side_conversation_create'] == true }
  end

  def people_permissions(cfg)
    { 'contacts.list' => cfg['end_user_list_access'] == 'full' ? 'full' : 'none',
      'contacts.edit' => %w[full edit edit-within-org].include?(cfg['end_user_profile_access']) ? 'full' : 'readonly',
      'contacts.views' => LEVELS3.include?(cfg['user_view_access']) ? cfg['user_view_access'] : 'readonly',
      'organizations.edit' => cfg['organization_editing'] == true, 'organizations.notes' => cfg['organization_notes_editing'] == true,
      'team_directory' => %w[none readonly all].include?(cfg['manage_team_members']) ? cfg['manage_team_members'] : 'none',
      'profile.edit_own' => cfg['update_user_own_name'] == true }
  end

  def tool_permissions(cfg)
    { 'macros' => MANAGE_LEVEL.fetch(cfg['macro_access'].to_s, 'readonly'),
      'views' => MANAGE_LEVEL.fetch(cfg['view_access'].to_s, 'readonly'), 'views.export' => cfg['export_views'] == true,
      'reports' => LEVELS3.include?(cfg['report_access']) ? cfg['report_access'] : 'none',
      'kb' => cfg['forum_access'] == 'full' ? 'full' : 'readonly', 'kb.restricted' => cfg['forum_access_restricted_content'] == true,
      'admin' => cfg['manage_roles'].to_s == 'all' || cfg['manage_triggers'] == true }
  end
end
