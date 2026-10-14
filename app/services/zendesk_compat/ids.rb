# IDs no formato do Zendesk (M7). Regra:
#   ticket        = conversations.display_id (= nº do ticket no Zendesk para os importados)
#   comentário    = messages.id (o mesmo do {{ticket.latest_comment.id}} dos webhooks do ServiceDesk)
#   usuário       = id de origem do Zendesk quando existe:
#                     agente  -> users.custom_attributes.zendesk_user_id
#                     bot     -> agent_bots.bot_config.zendesk_user_id
#                     contato -> identifier 'zd:<id>' / custom_attributes.zd_user_id
#                   sem id de origem: agente = USER_BASE + users.id, bot = BOT_BASE + agent_bots.id,
#                   contato = contacts.id (o mesmo do {{ticket.requester.id}} dos webhooks)
#   organização   = companies.custom_attributes.zd_org_id, ou ORG_BASE + companies.id
#   grupo         = id do grupo no Zendesk pelo nome do time (config), ou teams.id
# Os IDs do Zendesk têm 14 dígitos (~3,6e13) e os ids locais são pequenos: as faixas não se cruzam e todos
# cabem no inteiro seguro do JavaScript (2^53 ~ 9e15), que é como o n8n lê o JSON.
# rubocop:disable Metrics/CyclomaticComplexity
module ZendeskCompat::Ids
  USER_BASE = 1_000_000_000_000_000
  BOT_BASE = 3_000_000_000_000_000
  ORG_BASE = 4_000_000_000_000_000
  AUDIT_BASE = 5_000_000_000_000_000

  module_function

  def user_id(record)
    case record
    when User then origin_id(record.custom_attributes&.dig('zendesk_user_id')) || (USER_BASE + record.id)
    when AgentBot then origin_id(record.bot_config&.dig('zendesk_user_id')) || (BOT_BASE + record.id)
    when Contact then contact_id(record)
    end
  end

  def contact_id(contact)
    from_identifier = origin_id(contact.identifier.to_s.delete_prefix('zd:')) if contact.identifier.to_s.start_with?('zd:')
    from_identifier || origin_id(contact.custom_attributes&.dig('zd_user_id')) || contact.id
  end

  def organization_id(company)
    return if company.nil?

    origin_id(company.custom_attributes&.dig('zd_org_id')) || (ORG_BASE + company.id)
  end

  def origin_id(value)
    return if value.blank?

    integer = Integer(value.to_s, 10)
    integer.positive? ? integer : nil
  rescue ArgumentError, TypeError
    nil
  end

  def integer(value)
    Integer(value.to_s, 10)
  rescue ArgumentError, TypeError
    nil
  end
end
# rubocop:enable Metrics/CyclomaticComplexity
