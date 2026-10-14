# ServiceDesk M13: catálogo de permissões dos papéis (código CE próprio, sem enterprise/ e sem custom_roles).
#
# Cada chave tem um tipo (:bool ou uma lista ordenada de níveis, do menor para o maior) e o valor de perfis fixos:
# - ADMIN: tudo no nível máximo (Administrador e Administrador de faturamento do Zendesk);
# - CE_AGENT: o que um agente do Chatwoot CE faz hoje sem papel SD (account_user sem sd_role_id). Mantém o
#   comportamento original do CE para quem não recebeu papel (ex.: agente criado pela tela padrão);
# - NO_ACCESS: nada liberado (sem account_user).
# Os papéis padrão do Zendesk ficam em Servicedesk::Roles::Defaults.
module Servicedesk::Roles::Catalog
  TICKET_ACCESS_LEVELS = %w[all groups assigned requested].freeze

  KEYS = {
    'ticket.access' => TICKET_ACCESS_LEVELS,
    'ticket.comment_public' => :bool,
    'ticket.edit' => :bool,
    'ticket.edit_tags' => :bool,
    'ticket.assignable' => :bool,
    'ticket.assign_any_team' => :bool,
    'ticket.merge' => :bool,
    'ticket.delete' => :bool,
    'ticket.redact' => :bool,
    'ticket.modify_closed' => :bool,
    'ticket.view_deleted' => :bool,
    'contacts.list' => %w[none full],
    'contacts.edit' => %w[readonly full],
    'organizations.edit' => :bool,
    'macros' => %w[readonly personal full],
    'views' => %w[readonly personal full],
    'views.export' => :bool,
    'reports' => %w[none readonly full],
    'kb' => %w[readonly full],
    'profile.edit_own' => :bool,
    'team_directory' => %w[none readonly all],
    'suspended_tickets.manage' => :bool,
    'contacts.views' => %w[none readonly full],
    'organizations.notes' => :bool,
    'kb.restricted' => :bool,
    'side_conversations' => :bool,
    'admin' => :bool
  }.freeze

  # Chaves sem ponto de enforcement neste fork. ticket.merge, ticket.view_deleted e suspended_tickets.manage passaram
  # a valer com os módulos do Victor (mesclar, lixeira e suspensos). ticket.modify_closed fica sem efeito: o ticket
  # Fechado é somente leitura para todos (Conversation#closed_ticket_is_read_only), só as etiquetas mudam.
  # views.export (M3), contacts.views (user_view_access), organizations.notes, kb.restricted e side_conversations não
  # têm recurso equivalente no CE; admin (acesso às configurações) é garantido pelo papel base administrador.
  PENDING_KEYS = %w[ticket.modify_closed views.export contacts.views organizations.notes kb.restricted side_conversations].freeze

  # kb.restricted: forum_access_restricted_content, false até para o Administrador no Zendesk da B2B
  ADMIN = KEYS.transform_values { |type| type == :bool || type.last }.merge('ticket.access' => 'all', 'kb.restricted' => false).freeze

  NO_ACCESS = KEYS.transform_values { |type| type != :bool && type.first }.merge('ticket.access' => 'assigned').freeze

  CE_AGENT = ADMIN.merge(
    'ticket.delete' => false, 'ticket.view_deleted' => false, 'macros' => 'personal', 'views' => 'personal',
    'views.export' => false, 'reports' => 'none', 'kb' => 'readonly', 'team_directory' => 'readonly',
    'suspended_tickets.manage' => false, 'contacts.views' => 'readonly', 'kb.restricted' => false, 'admin' => false
  ).freeze

  module_function

  def keys
    KEYS.keys
  end

  def valid_value?(key, value)
    type = KEYS[key]
    return false if type.nil?
    return [true, false].include?(value) if type == :bool

    type.include?(value)
  end

  # Normaliza um hash vindo da API: só chaves conhecidas, booleanos convertidos, chave ausente = valor de base.
  def normalize(permissions, base: CE_AGENT)
    input = (permissions || {}).to_h.transform_keys(&:to_s)
    KEYS.keys.index_with { |key| normalize_one(key, input.key?(key) ? input[key] : base[key]) }
  end

  def invalid_keys(permissions)
    (permissions || {}).to_h.transform_keys(&:to_s).reject { |key, value| valid_value?(key, normalize_one(key, value)) }.keys
  end

  def normalize_one(key, value)
    KEYS[key] == :bool ? ActiveModel::Type::Boolean.new.cast(value) == true : value.to_s
  end

  # nível numérico de um valor (para comparar "pelo menos readonly")
  def level(key, value)
    type = KEYS.fetch(key)
    return value ? 1 : 0 if type == :bool

    type.index(value.to_s) || 0
  end
end
