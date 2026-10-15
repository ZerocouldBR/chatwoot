# Ordenações das views do Zendesk (`execution.sort_by`) que o Chatwoot não tem: SLA (próxima violação), ID do ticket,
# assunto, grupo, solicitante, canal, responsável, categoria do status, resolvido em e solicitante/responsável
# atualizados. Usadas pela lista de tickets (ConversationFinder e Conversations::FilterService, via
# Conversations::SortService). Os valores vêm de colunas do ticket (modelo do Victor: subject, next_sla_breach_at) ou
# de subconsultas correlacionadas (sem JOIN), para não colidir com os includes/preloads da lista.
# Sem valor fica sempre no fim, como no Zendesk; o desempate é a última atividade.
module Servicedesk::ConversationViewSorts
  extend ActiveSupport::Concern

  # Ordem das categorias de status do Zendesk no enum do Victor
  # (Novo, Aberto, Pendente, Em espera, Resolvido, Fechado; "Com o robô" junto com Aberto).
  STATUS_RANK = {
    'new_ticket' => 0, 'open' => 1, 'pending' => 1, 'waiting_on_customer' => 2, 'on_hold' => 3, 'resolved' => 4, 'closed' => 5
  }.freeze

  SORT_EXPRESSIONS = {
    'next_sla_breach_at' => 'conversations.next_sla_breach_at',
    'display_id' => 'conversations.display_id',
    'subject' => "LOWER(NULLIF(conversations.subject, ''))",
    'team_name' => '(SELECT LOWER(teams.name) FROM teams WHERE teams.id = conversations.team_id)',
    'requester_name' => "(SELECT LOWER(COALESCE(NULLIF(contacts.name, ''), contacts.email)) FROM contacts " \
                        'WHERE contacts.id = conversations.contact_id)',
    'inbox_name' => '(SELECT LOWER(inboxes.name) FROM inboxes WHERE inboxes.id = conversations.inbox_id)',
    'assignee_name' => '(SELECT LOWER(users.name) FROM users WHERE users.id = conversations.assignee_id)'
  }.freeze

  # Ordenações simples: sort_on_sd_next_sla_breach_at, sort_on_sd_display_id, sort_on_sd_subject, sort_on_sd_team_name,
  # sort_on_sd_requester_name, sort_on_sd_inbox_name e sort_on_sd_assignee_name.
  SIMPLE_SORTS = SORT_EXPRESSIONS.keys.freeze

  class_methods do
    SIMPLE_SORTS.each do |name|
      define_method("sort_on_sd_#{name}") { |sort_direction = :asc| sd_reorder(SORT_EXPRESSIONS.fetch(name), sort_direction) }
    end

    # Resolvido em: última mudança para Resolvido na auditoria do ticket (conversation_events); no histórico
    # importado (sem evento), a última atividade do ticket resolvido ou fechado.
    def sort_on_sd_solved_at(sort_direction = :desc)
      sd_reorder(Servicedesk::TicketClocks.solved_at_sql(statuses), sort_direction)
    end

    def sort_on_sd_requester_updated_at(sort_direction = :desc)
      sd_reorder(Servicedesk::TicketClocks::REQUESTER_UPDATED_SQL, sort_direction)
    end

    def sort_on_sd_assignee_updated_at(sort_direction = :desc)
      sd_reorder(Servicedesk::TicketClocks::ASSIGNEE_UPDATED_SQL, sort_direction)
    end

    # Categoria do status, na ordem do Zendesk
    def sort_on_sd_status_category(sort_direction = :asc)
      cases = STATUS_RANK.map { |status, rank| "WHEN #{statuses.fetch(status)} THEN #{rank}" }
      sd_reorder("(CASE conversations.status #{cases.join(' ')} ELSE 1 END)", sort_direction)
    end

    private

    def sd_reorder(expression, sort_direction)
      direction = sort_direction.to_s.casecmp('desc').zero? ? 'DESC' : 'ASC'
      reorder(Arel.sql("#{expression} #{direction} NULLS LAST, conversations.last_activity_at DESC, conversations.id DESC"))
    end
  end
end
