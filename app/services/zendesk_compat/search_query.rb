# GET /api/v2/search?query=... (sintaxe de busca do Zendesk, subconjunto usado pelos workflows e comum em automações):
#   type:ticket|user|organization   status:x / status<x / status<=x / status>x / status>=x   (new<open<pending<hold<solved<closed)
#   assignee:<id|email|none|me>   group:<id|nome|none>   requester:<id|email>   organization:<id>   tags:x / -tags:x
#   created / updated / solved com : < > <= >= e data (AAAA-MM-DD), data-hora ISO ou relativo (2hours, 3days, 1week...)
#   priority:x  via:email|whatsapp|...  custom_field_<id>:valor  ticket_id/id  e texto livre (assunto)
# Termos desconhecidos -> ZendeskCompat::Error::Unsupported (400), para o workflow não receber um resultado errado em silêncio.
# rubocop:disable Metrics/AbcSize, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
class ZendeskCompat::SearchQuery
  TOKEN = /(-)?([a-z_0-9]+)(<=|>=|:|<|>)("[^"]*"|\S+)|"[^"]*"|\S+/
  RELATIVE = /\A(\d+)(minutes?|hours?|days?|weeks?|months?|years?)\z/
  OPERATORS = { ':' => '=', '<' => '<', '>' => '>', '<=' => '<=', '>=' => '>=' }.freeze

  attr_reader :type

  def initialize(context, query)
    @context = context
    @query = query.to_s
    @type = 'ticket'
    @conditions = []
    @text = []
    parse
  end

  def tickets
    scope = @context.account.conversations.includes(:contact, :assignee, :team, :inbox)
    @conditions.each { |condition| scope = condition.call(scope) }
    @text.each { |word| scope = scope.where("#{ZendeskCompat::TicketModel.subject_sql} ILIKE ?", "%#{sanitize(word)}%") }
    scope
  end

  def users
    words = @text.map { |word| sanitize(word) }
    contacts = @context.account.contacts
    agents = @context.account.users
    words.each do |word|
      contacts = contacts.where('contacts.email ILIKE :w OR contacts.name ILIKE :w OR contacts.phone_number ILIKE :w', w: "%#{word}%")
      agents = agents.where('users.email ILIKE :w OR users.name ILIKE :w', w: "%#{word}%")
    end
    agents.limit(1000).to_a + contacts.limit(1000).to_a
  end

  private

  def parse
    @query.scan(TOKEN) do
      match = Regexp.last_match
      if match[2]
        apply(match[2], match[3], match[4].delete('"'), negated: match[1].present?)
      elsif match[0].present?
        @text << match[0].delete('"')
      end
    end
  end

  def apply(key, operator, value, negated:)
    case key
    when 'type' then @type = value
    when 'status' then status(operator, value)
    when 'assignee' then assignee(value, negated)
    when 'group' then group(value, negated)
    when 'tags', 'tag' then tags(value, negated)
    when 'created', 'updated', 'solved' then date(key, operator, value)
    when 'requester' then requester(value)
    when 'priority' then priority(value)
    when 'via' then via(value)
    when 'ticket_id', 'id' then add { |s| s.where(display_id: value.to_i) }
    when /\Acustom_field_(\d+)\z/ then custom_field(Regexp.last_match(1), value)
    else raise ZendeskCompat::Error::Unsupported, "Termo de busca não suportado pelo ServiceDesk: #{key}#{operator}#{value}"
    end
  end

  def add(&block)
    @conditions << block
  end

  def status(operator, value)
    order = ZendeskCompat::StatusTranslator::ORDER
    index = order.index(value.downcase) || raise(ZendeskCompat::Error, "Status inválido na busca: #{value}")
    categories = case operator
                 when ':' then [order[index]]
                 when '<' then order[0...index]
                 when '<=' then order[0..index]
                 when '>' then order[(index + 1)..]
                 else order[index..]
                 end
    add { |s| s.where("#{ZendeskCompat::StatusTranslator.category_sql} IN (?)", categories) }
  end

  def assignee(value, negated)
    if value == 'none'
      return add { |s| negated ? s.where.not(assignee_id: nil) : s.where(assignee_id: nil) }
    end

    record = if value == 'me'
               @context.user
             else
               (value.include?('@') ? @context.directory.agent_by_email(value) : @context.directory.actor(value))
             end
    if record.is_a?(AgentBot)
      return add { |s| negated ? s.where.not(assignee_agent_bot_id: record.id) : s.where(assignee_agent_bot_id: record.id) }
    end

    user_id = record.is_a?(User) ? record.id : 0
    add { |s| negated ? s.where.not(assignee_id: user_id).or(s.where(assignee_id: nil)) : s.where(assignee_id: user_id) }
  end

  def group(value, negated)
    return add { |s| negated ? s.where.not(team_id: nil) : s.where(team_id: nil) } if value == 'none'

    team = @context.directory.team(value) || @context.account.teams.where('LOWER(name) = ?', value.downcase).first
    team_id = team&.id || 0
    add { |s| negated ? s.where.not(team_id: team_id).or(s.where(team_id: nil)) : s.where(team_id: team_id) }
  end

  def tags(value, negated)
    tag = ZendeskCompat::Tags.normalize_one(value)
    add { |s| s.tagged_with(tag, on: :labels, exclude: negated) }
  end

  def date(key, operator, value)
    time = parse_time(value)
    column = { 'created' => 'conversations.created_at', 'updated' => 'conversations.updated_at', 'solved' => 'conversations.status_changed_at' }[key]
    sql_operator = OPERATORS[operator]
    if operator == ':' && value.match?(/\A\d{4}-\d{2}-\d{2}\z/)
      add { |s| s.where("#{column} >= ? AND #{column} < ?", time, time + 1.day) }
    else
      add { |s| s.where("#{column} #{sql_operator} ?", time) }
    end
    add { |s| s.where(status: ZendeskCompat::TicketModel.solved_statuses) } if key == 'solved'
  end

  def parse_time(value)
    relative = value.match(RELATIVE)
    return relative[1].to_i.public_send(relative[2]).ago if relative

    Time.zone.parse(value) || raise(ArgumentError)
  rescue ArgumentError
    raise ZendeskCompat::Error, "Data inválida na busca: #{value}"
  end

  def requester(value)
    record = value.include?('@') ? @context.directory.contact_by_email(value) : @context.directory.actor(value)
    record = @context.directory.contact_by_email(record.email) if record.is_a?(User)
    contact_id = record.is_a?(Contact) ? record.id : 0
    add { |s| s.where(contact_id: contact_id) }
  end

  def priority(value)
    native = ZendeskCompat::Config.priorities[value.downcase]
    add { |s| s.where(priority: native) }
  end

  def via(value)
    label = ZendeskCompat::Config.via_channels[value.downcase]
    add { |s| s.where("conversations.custom_attributes->>'zd_canal' = ?", label) }
  end

  def custom_field(field_id, value)
    key, stored = @context.fields.search_value(field_id, value)
    raise ZendeskCompat::Error::Unsupported, "Campo desconhecido na busca: custom_field_#{field_id}" if key.nil?

    add { |s| s.where('conversations.custom_attributes->>? = ?', key, stored.to_s) }
  end

  def sanitize(word)
    ActiveRecord::Base.sanitize_sql_like(word)
  end
end
# rubocop:enable Metrics/AbcSize, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
