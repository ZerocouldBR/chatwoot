# ServiceDesk M13: os papéis do Zendesk da B2B Reservas (custom_roles.json + papel embutido Agente; conferido com a
# API em 14/10/2026: 18 Administrador, 27 Agente, 32 Agente light, 2 Colaborador, 0 Administrador de faturamento).
# Os 4 papéis personalizados são exatamente Servicedesk::Roles::ZendeskMapper.permissions(configuration) do
# custom_roles.json (spec/services/servicedesk/roles/zendesk_mapper_spec.rb confere). O papel embutido Agente não
# é exposto pela API: valores do plano Professional (PERMISSOES.md §2).
module Servicedesk::Roles::Defaults
  AGENTE = Servicedesk::Roles::Catalog::ADMIN.merge(
    'ticket.redact' => false, 'ticket.modify_closed' => false, 'ticket.view_deleted' => false,
    'organizations.edit' => false, 'macros' => 'personal', 'views' => 'personal', 'views.export' => false,
    'reports' => 'none', 'kb' => 'readonly', 'team_directory' => 'readonly', 'suspended_tickets.manage' => false,
    'contacts.views' => 'readonly', 'organizations.notes' => false, 'kb.restricted' => false, 'admin' => false
  ).freeze

  # "Pode visualizar e adicionar comentários privados aos tickets"
  AGENTE_LIGHT = AGENTE.merge(
    'ticket.comment_public' => false, 'ticket.edit' => false, 'ticket.edit_tags' => false, 'ticket.assignable' => false,
    'ticket.assign_any_team' => false, 'ticket.merge' => false, 'ticket.delete' => false, 'contacts.edit' => 'readonly',
    'macros' => 'readonly', 'views' => 'readonly', 'views.export' => true, 'reports' => 'readonly',
    'profile.edit_own' => false, 'suspended_tickets.manage' => true, 'contacts.views' => 'none'
  ).freeze

  # "Pode oferecer suporte limitado": só os tickets dos próprios grupos (ticket_access=within-groups)
  COLABORADOR = AGENTE_LIGHT.merge(
    'ticket.access' => 'groups', 'contacts.list' => 'none', 'views.export' => false, 'reports' => 'none',
    'team_directory' => 'none', 'suspended_tickets.manage' => false
  ).freeze

  ADMIN = Servicedesk::Roles::Catalog::ADMIN

  # key => atributos do papel padrão. base_role: 'administrator' ou 'agent' (AccountUser.role).
  ROLES = {
    'administrador' => {
      name: 'Administrador', base_role: 'administrator', zendesk_custom_role_id: 20_487_414_623_259, position: 1,
      description: 'Pode gerenciar todas as configurações, exceto faturamento', permissions: ADMIN
    },
    'administrador_faturamento' => {
      name: 'Administrador de faturamento', base_role: 'administrator', zendesk_custom_role_id: 20_487_422_486_811, position: 2,
      description: 'Pode gerenciar todas as configurações, incluindo faturamento (sem faturamento no ServiceDesk)', permissions: ADMIN
    },
    'agente' => {
      name: 'Agente', base_role: 'agent', zendesk_custom_role_id: nil, position: 3,
      description: 'Papel padrão de agente: vê todos os tickets, responde, edita e exclui tickets', permissions: AGENTE
    },
    'agente_light' => {
      name: 'Agente light', base_role: 'agent', zendesk_custom_role_id: 20_487_384_045_211, position: 4,
      description: 'Pode visualizar e adicionar comentários privados aos tickets', permissions: AGENTE_LIGHT
    },
    'colaborador' => {
      name: 'Colaborador', base_role: 'agent', zendesk_custom_role_id: 20_487_422_341_915, position: 5,
      description: 'Pode oferecer suporte limitado: só os tickets dos próprios grupos e só nota interna', permissions: COLABORADOR
    }
  }.freeze
end
