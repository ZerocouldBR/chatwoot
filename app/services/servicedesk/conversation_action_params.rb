# Parâmetros das ações do ServiceDesk usadas por macros e automações (M5/M4):
#
#   set_custom_attribute  [chave, valor]  grava um atributo de conversa respeitando o tipo (e a lista, no tipo list).
#                                         Valor vazio limpa o atributo. `zd_status` não é aceito: use set_ticket_status.
#   set_ticket_status     [rótulo]        grava o rótulo em zd_status e aplica o status nativo da categoria
#                                         (config/servicedesk/ticket_statuses.yml).
#   change_subject        [assunto]       grava o assunto do ticket (coluna subject) e o do próximo e-mail (mail_subject).
#
# Os parâmetros ficam como array de escalares para caberem no `action_params: []` dos controllers e no
# gerador de payload do frontend (actionQueryGenerator).
class Servicedesk::ConversationActionParams
  ACTION_NAMES = %w[set_custom_attribute set_ticket_status change_subject].freeze
  SUBJECT_MAX_LENGTH = 500
  TEXT_MAX_LENGTH = 10_000
  # O regex_pattern vem da definição do atributo (admin); o valor pode vir de uma macro pessoal de agente.
  REGEX_TIMEOUT = 0.5
  TRUE_VALUES = [true, 'true', '1', 1].freeze
  FALSE_VALUES = [false, 'false', '0', 0].freeze

  Result = Struct.new(:value, :error) do
    def ok?
      error.nil?
    end
  end

  def initialize(account)
    @account = account
  end

  # Mensagens de erro para as ações do ServiceDesk de uma lista de ações (as demais são ignoradas).
  def errors_for(actions)
    Array(actions).filter_map do |action|
      action = action.to_h.with_indifferent_access
      name = action[:action_name].to_s
      next unless ACTION_NAMES.include?(name)

      error = send("params_error_#{name}", Array(action[:action_params]))
      "#{name}: #{error}" if error
    end
  end

  # set_custom_attribute: devolve Result com o valor já convertido (nil = limpar) ou o erro.
  def custom_attribute(key, value)
    return Result.new(nil, 'chave do atributo ausente') if key.blank?
    return Result.new(nil, "use set_ticket_status para #{key}") if key.to_s == Servicedesk::TicketStatuses.attribute_key

    definition = conversation_attribute(key)
    return Result.new(nil, "atributo de conversa inexistente: #{key}") unless definition
    return Result.new(nil, nil) if value.nil? || value.to_s.strip.empty?

    cast(definition, value)
  end

  # set_ticket_status: devolve o status (hash do yml) ou o erro.
  def ticket_status(label)
    status = Servicedesk::TicketStatuses.find(label)
    return Result.new(nil, "status desconhecido: #{label}") unless status

    definition = conversation_attribute(Servicedesk::TicketStatuses.attribute_key)
    if definition&.list? && Array(definition.attribute_values).exclude?(status['label'])
      return Result.new(nil, "status fora da lista de #{definition.attribute_key}: #{status['label']}")
    end

    Result.new(status, nil)
  end

  def subject(value)
    subject = value.to_s.squish
    return Result.new(nil, 'assunto vazio') if subject.empty?
    return Result.new(nil, "assunto com mais de #{SUBJECT_MAX_LENGTH} caracteres") if subject.length > SUBJECT_MAX_LENGTH

    Result.new(subject, nil)
  end

  private

  def params_error_set_custom_attribute(params)
    return 'parâmetros esperados: [chave, valor]' unless params.size == 2 && scalar?(params[0]) && scalar?(params[1])

    custom_attribute(params[0], params[1]).error
  end

  def params_error_set_ticket_status(params)
    return 'parâmetro esperado: [rótulo do status]' unless params.size == 1 && scalar?(params[0])

    ticket_status(params[0]).error
  end

  def params_error_change_subject(params)
    return 'parâmetro esperado: [assunto]' unless params.size == 1 && scalar?(params[0])

    subject(params[0]).error
  end

  def scalar?(value)
    value.nil? || value.is_a?(String) || value.is_a?(Numeric) || value == true || value == false
  end

  def conversation_attribute(key)
    @definitions ||= {}
    return @definitions[key.to_s] if @definitions.key?(key.to_s)

    @definitions[key.to_s] = @account.custom_attribute_definitions.find_by(attribute_key: key.to_s,
                                                                           attribute_model: 'conversation_attribute')
  end

  def cast(definition, value)
    case definition.attribute_display_type
    when 'list' then cast_list(definition, value)
    when 'checkbox' then cast_checkbox(value)
    when 'number', 'currency', 'percent' then cast_number(value)
    when 'date' then cast_date(value)
    when 'link' then cast_link(value)
    else cast_text(definition, value)
    end
  end

  def cast_list(definition, value)
    text = value.to_s
    return Result.new(text, nil) if Array(definition.attribute_values).include?(text)

    Result.new(nil, "valor fora da lista de #{definition.attribute_key}: #{text}")
  end

  def cast_checkbox(value)
    return Result.new(true, nil) if TRUE_VALUES.include?(value)
    return Result.new(false, nil) if FALSE_VALUES.include?(value)

    Result.new(nil, "valor inválido para checkbox: #{value}")
  end

  def cast_number(value)
    return Result.new(value, nil) if value.is_a?(Numeric)

    text = value.to_s.strip
    return Result.new(Integer(text, 10), nil) if text.match?(/\A-?\d+\z/)
    return Result.new(Float(text), nil) if text.match?(/\A-?\d+\.\d+\z/)

    Result.new(nil, "valor numérico inválido: #{value}")
  end

  def cast_date(value)
    Result.new(Date.iso8601(value.to_s.strip[0, 10]).iso8601, nil)
  rescue Date::Error
    Result.new(nil, "data inválida (use AAAA-MM-DD): #{value}")
  end

  def cast_link(value)
    text = value.to_s.strip
    return Result.new(text, nil) if text.match?(%r{\Ahttps?://\S+\z}i)

    Result.new(nil, "link inválido: #{value}")
  end

  def cast_text(definition, value)
    text = value.to_s
    return Result.new(nil, "texto com mais de #{TEXT_MAX_LENGTH} caracteres") if text.length > TEXT_MAX_LENGTH
    if definition.regex_pattern.present? && !text_regex(definition).match?(text)
      return Result.new(nil, "valor não segue o formato de #{definition.attribute_key}")
    end

    Result.new(text, nil)
  rescue Regexp::TimeoutError
    Result.new(nil, "valor não segue o formato de #{definition.attribute_key} (tempo de validação esgotado)")
  rescue RegexpError
    Result.new(text, nil)
  end

  def text_regex(definition)
    Regexp.new(definition.regex_pattern.delete_prefix('/').delete_suffix('/'), timeout: REGEX_TIMEOUT)
  end
end
