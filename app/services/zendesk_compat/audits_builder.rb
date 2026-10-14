# Audits do ticket no formato do Zendesk (GET /api/v2/tickets/:id/audits), em ordem cronológica:
#   1º audit = criação: eventos Create (status, responsável, grupo, prioridade, etiquetas) + o 1º comentário
#   um audit por comentário (mensagem pública ou nota interna), id = id da mensagem
#   um audit por alteração registrada (ZendeskCompat::AuditSource: sd_ticket_audits ou conversation_events), id = AUDIT_BASE + id
# Sem registro da criação (modelo legado, tickets importados), o Create usa os valores de antes da 1ª alteração
# registrada (ou os atuais).
class ZendeskCompat::AuditsBuilder
  CREATE_BASE = 6_000_000_000_000_000
  CREATE_FIELDS = %w[status custom_status_id assignee_id group_id priority tags].freeze

  def initialize(context, conversation)
    @context = context
    @conversation = conversation
    @comments = ZendeskCompat::CommentPresenter.new(context)
    @source = ZendeskCompat::AuditSource.for(conversation)
  end

  def audits
    messages = ZendeskCompat::CommentPresenter.comment_scope(@conversation).order(:created_at, :id).to_a
    rows = @source.rows
    list = comment_audits(messages) + rows.map { |row| change_audit(row) }
    attach_create_events(list, messages.first, rows)
    list.sort_by { |audit| [audit[:created_at].to_s, audit[:id]] }
  end

  # Id da última alteração registrada (para o request_audit de um PUT).
  def last_change_id
    @source.last_id
  end

  # Audit da requisição (resposta de PUT/POST de ticket): alterações registradas depois de after_change_id + o comentário,
  # num audit só, como o Zendesk devolve.
  def request_audit(after_change_id:, message: nil)
    parts = @source.rows(after_id: after_change_id.to_i).map { |row| change_audit(row) }
    parts += comment_audits([message]) if message
    return base(nil, Time.current, ZendeskCompat::Ids.user_id(@context.user), 'api') if parts.empty?

    parts.first.merge(events: parts.flat_map { |audit| audit[:events] })
  end

  private

  def base(id, created_at, author_id, channel)
    {
      id: id, ticket_id: @conversation.display_id, created_at: @context.time(created_at), author_id: author_id,
      metadata: { system: {}, custom: {} }, via: { channel: channel, source: { from: {}, to: {}, rel: nil } }, events: []
    }
  end

  def comment_audits(messages)
    messages.map do |message|
      comment = @comments.present(message)
      event = comment.slice(:id, :author_id, :body, :html_body, :plain_body, :public, :attachments, :audit_id).merge(type: 'Comment')
      base(message.id, message.created_at, comment[:author_id], comment[:via][:channel]).merge(events: [event])
    end
  end

  def change_audit(row)
    author_id = row[:author] ? ZendeskCompat::Ids.user_id(row[:author]) : -1
    events = row[:events].each_with_index.map do |event, index|
      event.symbolize_keys.merge(id: (row[:id] * 100) + index + 1, type: event['type'] || 'Change')
    end
    base(ZendeskCompat::Ids::AUDIT_BASE + row[:id], row[:created_at], author_id, row[:via]).merge(events: events)
  end

  def attach_create_events(list, first_message, rows)
    events = create_events(rows)
    first_audit = first_message && list.find { |audit| audit[:id] == first_message.id }
    if first_audit
      first_audit[:events] = events + first_audit[:events]
      first_audit[:created_at] = [first_audit[:created_at], @context.time(@conversation.created_at)].min
    else
      list << base(CREATE_BASE + @conversation.id, @conversation.created_at, -1, 'api').merge(events: events)
    end
  end

  def create_events(rows)
    recorded = @source.create_values
    current = current_values
    CREATE_FIELDS.each_with_index.filter_map do |field, index|
      value = create_value(field, recorded, rows, current)
      next if value.nil? || value == []

      { id: (@conversation.id * 100) + index + 1, type: 'Create', field_name: field, value: value }
    end
  end

  def create_value(field, recorded, rows, current)
    return recorded[field] if recorded&.key?(field)

    first_change = rows.flat_map { |row| row[:events] }.find { |event| event['field_name'] == field }
    first_change ? first_change['previous_value'] : current[field]
  end

  def current_values
    ticket = ZendeskCompat::TicketPresenter.new(@context).present(@conversation)
    {
      'status' => ticket[:status], 'custom_status_id' => ticket[:custom_status_id]&.to_s, 'assignee_id' => ticket[:assignee_id]&.to_s,
      'group_id' => ticket[:group_id]&.to_s, 'priority' => ticket[:priority], 'tags' => ticket[:tags]
    }
  end
end
