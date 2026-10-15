# Relógios do ticket usados pelas colunas e ordenações das views do Zendesk:
#   solved_at             última mudança para Resolvido (auditoria do Victor, conversation_events); sem evento
#                         (histórico importado), a última atividade do ticket resolvido ou fechado;
#   requester_updated_at  última mensagem recebida do cliente;
#   assignee_updated_at   última resposta pública ou nota do responsável atual.
#
# Na lista, `preload` calcula os três para a página inteira numa consulta só (sem N+1) e guarda em cada conversa;
# fora da lista (um ticket só), `for` consulta na hora.
class Servicedesk::TicketClocks
  REQUESTER_UPDATED_SQL = '(SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = conversations.id ' \
                          'AND m.message_type = 0)'.freeze
  ASSIGNEE_UPDATED_SQL = '(SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = conversations.id ' \
                         "AND m.message_type = 1 AND m.sender_type = 'User' AND m.sender_id = conversations.assignee_id)".freeze

  class << self
    def solved_at_sql(statuses)
      event = '(SELECT MAX(e.created_at) FROM conversation_events e WHERE e.conversation_id = conversations.id AND ' \
              "e.field_name = 'status' AND e.value = '\"resolved\"'::jsonb)"
      "COALESCE(#{event}, CASE WHEN conversations.status IN (#{statuses['resolved']}, #{statuses['closed']}) " \
        'THEN conversations.last_activity_at END)'
    end

    # Carrega a relação (a mesma instância que a view vai percorrer) e grava o relógio de cada conversa.
    def preload(conversations)
      records = conversations.respond_to?(:load) ? conversations.load.to_a : Array(conversations)
      return conversations if records.empty?

      clocks = fetch(records.map(&:id))
      records.each { |conversation| conversation.sd_clock = clocks[conversation.id] || empty }
      conversations
    end

    def for(conversation)
      fetch([conversation.id])[conversation.id] || empty
    end

    private

    def fetch(ids)
      rows = Conversation.unscoped.where(id: ids).pluck(
        :id,
        Arel.sql(solved_at_sql(Conversation.statuses)),
        Arel.sql(REQUESTER_UPDATED_SQL),
        Arel.sql(ASSIGNEE_UPDATED_SQL)
      )
      rows.to_h do |id, solved, requester, assignee|
        [id, { solved_at: solved&.to_i, requester_updated_at: requester&.to_i, assignee_updated_at: assignee&.to_i }]
      end
    end

    def empty
      { solved_at: nil, requester_updated_at: nil, assignee_updated_at: nil }
    end
  end
end
