# ServiceDesk M13: permissões efetivas de um account_user.
#
#   access = Servicedesk::Roles::Access.for(account_user)
#   access.can?('ticket.edit')            # booleano
#   access.at_least?('reports', 'readonly')
#   access.ticket_access                  # 'all' | 'groups' | 'assigned' | 'requested'
#
# Regras:
# - administrador (AccountUser.role = administrator): tudo liberado, como no Zendesk;
# - agente com papel SD (sd_role_id): permissões do papel;
# - agente sem papel SD: perfil CE_AGENT (o comportamento original do Chatwoot CE);
# - ticket_access_override (ticket_restriction do usuário no Zendesk) substitui ticket.access do papel;
# - only_private_comments (do usuário) tira ticket.comment_public.
class Servicedesk::Roles::Access
  attr_reader :account_user

  def self.for(account_user)
    account_user.nil? ? new(nil) : account_user.sd_access
  end

  def initialize(account_user)
    @account_user = account_user
  end

  def administrator?
    account_user&.administrator? == true
  end

  def role_key
    account_user&.sd_role&.key
  end

  def permissions
    @permissions ||= build_permissions
  end

  def value(key)
    permissions.fetch(key.to_s)
  end

  def can?(key)
    value = permissions.fetch(key.to_s)
    value == true || (value.is_a?(String) && %w[none readonly].exclude?(value))
  end

  def at_least?(key, minimum)
    Servicedesk::Roles::Catalog.level(key, value(key)) >= Servicedesk::Roles::Catalog.level(key, minimum)
  end

  def ticket_access
    value('ticket.access')
  end

  def restricted_ticket_access?
    ticket_access != 'all'
  end

  def suspended?
    account_user&.suspended_at.present?
  end

  # Lista que vai para o frontend em account.permissions (além de 'administrator'/'agent'):
  #   'sd:<chave>' quando a permissão está liberada (booleano true ou nível acima de none/readonly)
  #   'sd:<chave>:<valor>' para as chaves de nível (ex.: 'sd:reports:readonly', 'sd:ticket.access:groups')
  #   'sd_role:<key>' com o papel (quando houver)
  def permission_strings
    list = permissions.flat_map do |key, value|
      items = []
      items << "sd:#{key}" if can?(key)
      items << "sd:#{key}:#{value}" if value.is_a?(String)
      items
    end
    list.unshift("sd_role:#{role_key}") if role_key
    list
  end

  private

  def build_permissions
    return Servicedesk::Roles::Catalog::NO_ACCESS if account_user.nil?
    return Servicedesk::Roles::Catalog::ADMIN.dup if administrator?

    base = role_permissions
    base = base.merge('ticket.access' => account_user.ticket_access_override) if override_access?
    base = base.merge('ticket.comment_public' => false) if account_user&.only_private_comments
    base
  end

  def role_permissions
    role = account_user&.sd_role
    return Servicedesk::Roles::Catalog::CE_AGENT.dup if role.nil?

    Servicedesk::Roles::Catalog.normalize(role.permissions, base: Servicedesk::Roles::Catalog::CE_AGENT)
  end

  def override_access?
    Servicedesk::Roles::Catalog::TICKET_ACCESS_LEVELS.include?(account_user&.ticket_access_override.to_s)
  end
end
