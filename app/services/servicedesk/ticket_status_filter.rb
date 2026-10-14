# ServiceDesk: filtro de status da lista no padrão do Agent Workspace.
#
# Pelo status canônico, Pendente e Em espera usam o mesmo status nativo
# (snoozed) e se distinguem pela categoria do rótulo `zd_status`:
#   - Em espera (hold): snoozed com zd_status de categoria "hold";
#   - Pendente (pending): os demais snoozed (zd_status de categoria "pending",
#     vazio ou desconhecido), igual ao que a tela mostra (statusTokens.js).
# Assim cada ticket snoozed cai em exatamente um dos dois filtros.
#
# HOLD_LABELS vem de config/servicedesk/ticket_statuses.yml (Servicedesk::TicketStatuses,
# a mesma fonte da ação set_ticket_status); as specs conferem o yml e esta lista
# contra app/javascript/dashboard/servicedesk/ticketFormsMeta.json.
module Servicedesk::TicketStatusFilter
  CATEGORIES = %w[pending hold].freeze

  HOLD_LABELS = Servicedesk::TicketStatuses.statuses.select { |status| status['category'] == 'hold' }.pluck('label').freeze

  ZD_STATUS_SQL = "LOWER(TRIM(conversations.custom_attributes ->> 'zd_status'))".freeze

  module_function

  # conversations: relation já filtrada por status snoozed.
  # category: 'pending' | 'hold' (qualquer outro valor não filtra).
  def apply(conversations, category)
    case category.to_s
    when 'hold'
      conversations.where("#{ZD_STATUS_SQL} IN (?)", hold_keys)
    when 'pending'
      conversations.where("COALESCE(#{ZD_STATUS_SQL}, '') NOT IN (?)", hold_keys)
    else
      conversations
    end
  end

  # Rótulos em minúsculas, com e sem acento (o front compara sem acento).
  def hold_keys
    @hold_keys ||= HOLD_LABELS.flat_map { |label| [label.downcase, I18n.transliterate(label).downcase] }.uniq.freeze
  end
end
