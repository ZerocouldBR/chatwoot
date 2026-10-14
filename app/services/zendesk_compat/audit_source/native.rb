# Alterações gravadas em conversation_events (modelo nativo f10), traduzidas para os nomes e valores do Zendesk.
class ZendeskCompat::AuditSource::Native
  FIELDS = { 'status' => 'status', 'priority' => 'priority', 'assignee_id' => 'assignee_id', 'team_id' => 'group_id',
             'subject' => 'subject', 'ticket_type' => 'type', 'due_at' => 'due_at', 'company_id' => 'organization_id',
             'contact_id' => 'requester_id', 'problem_id' => 'problem_id', 'satisfaction' => 'satisfaction_score',
             'cached_label_list' => 'tags' }.freeze
  VIAS = { 'agent' => 'web', 'customer' => 'web', 'rule' => 'rule', 'bot' => 'api', 'system' => 'system' }.freeze
  PRIORITIES = { 'low' => 'low', 'medium' => 'normal', 'high' => 'high', 'urgent' => 'urgent' }.freeze

  def initialize(conversation)
    @conversation = conversation
    @directory = ZendeskCompat::Directory.new(conversation.account)
  end

  def rows(after_id: nil)
    scope = events_scope.where(event_type: 'change')
    scope = scope.where('id > ?', after_id.to_i) if after_id
    scope.to_a.chunk_while { |a, b| same_update?(a, b) }.map { |group| row(group) }
  end

  def last_id
    ConversationEvent.where(conversation_id: @conversation.id).maximum(:id)
  end

  # Valores da criação (evento "create"), já no formato do Zendesk: { 'status' => 'new', 'group_id' => '...' }
  def create_values
    created = ConversationEvent.where(conversation_id: @conversation.id).order(:id).find_by(event_type: 'create')
    return if created.nil?

    (created.value || {}).each_with_object({}) do |(field, raw), memo|
      name = FIELDS[field]
      memo[name] = translate(field, raw) if name
    end
  end

  private

  def events_scope
    ConversationEvent.where(conversation_id: @conversation.id).includes(:author).order(:id)
  end

  def same_update?(first, second)
    first.created_at.to_i == second.created_at.to_i && first.author_type == second.author_type &&
      first.author_id == second.author_id && first.via == second.via
  end

  def row(group)
    first = group.first
    author = first.author if first.author.is_a?(User) || first.author.is_a?(AgentBot) || first.author.is_a?(Contact)
    events = group.filter_map do |event|
      name = FIELDS[event.field_name]
      next unless name

      { 'type' => 'Change', 'field_name' => name, 'value' => translate(event.field_name, event.value),
        'previous_value' => translate(event.field_name, event.previous_value) }
    end
    { id: first.id, created_at: first.created_at, author: author, via: VIAS.fetch(first.via, 'web'), events: events }
  end

  # rubocop:disable Metrics/CyclomaticComplexity, Metrics/AbcSize, Metrics/PerceivedComplexity
  def translate(field, raw)
    return nil if raw.nil? || raw == ''

    case field
    when 'status' then ZendeskCompat::StatusTranslator::ENUM_CATEGORY[enum_name(:statuses, raw)]
    when 'priority' then PRIORITIES[enum_name(:priorities, raw)]
    when 'ticket_type' then enum_name(:ticket_types, raw)
    when 'assignee_id' then record_id(User.find_by(id: raw))
    when 'contact_id' then record_id(Contact.find_by(id: raw))
    when 'team_id' then @directory.group_id(Team.find_by(id: raw))&.to_s
    when 'company_id' then ZendeskCompat::Ids.organization_id(Company.find_by(id: raw))&.to_s
    when 'problem_id' then Conversation.find_by(id: raw)&.display_id&.to_s
    when 'cached_label_list' then raw.to_s.split(',').map(&:strip).compact_blank.sort
    else raw.to_s
    end
  end
  # rubocop:enable Metrics/CyclomaticComplexity, Metrics/AbcSize, Metrics/PerceivedComplexity

  def enum_name(enum, raw)
    values = Conversation.public_send(enum)
    raw.is_a?(Integer) ? values.key(raw) : raw.to_s
  end

  def record_id(record)
    record && ZendeskCompat::Ids.user_id(record).to_s
  end
end
