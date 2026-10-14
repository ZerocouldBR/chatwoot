# Campos personalizados do Zendesk (custom_fields [{id, value}]) <-> atributos da conversa (zd_*).
# Campo -> atributo: definição da conta com descrição "zendesk_field:<id>" (provision_fields_extra.rb); na falta, a chave
# do mapa (config). Lista: o atributo guarda o NOME da opção e a API devolve/aceita a TAG; checkbox: true/ausente;
# texto longo: o valor completo fica em additional_attributes.zendesk.long_values (importação).
# rubocop:disable Metrics/CyclomaticComplexity
class ZendeskCompat::FieldTranslator
  FIELD_PREFIX = 'zendesk_field:'.freeze

  def initialize(account)
    @account = account
  end

  # [{id:, value:}] de todos os campos personalizados (não-sistema), como o Zendesk devolve.
  def custom_fields(conversation)
    attributes = conversation.custom_attributes || {}
    long_values = conversation.additional_attributes&.dig('zendesk', 'long_values') || {}
    ZendeskCompat::Config.custom_ticket_fields.map do |field|
      key = attribute_key(field)
      raw = long_values[field['id'].to_s].presence || (key && attributes[key])
      { id: field['id'], value: zendesk_value(field, raw) }
    end
  end

  # custom_fields/fields do Zendesk -> {chave => valor}; ids desconhecidos são ignorados (como o Zendesk faz).
  # Aceita [{id:, value:}] ou {id => value}.
  def attributes_from(custom_fields)
    pairs = custom_fields.is_a?(Hash) ? custom_fields.to_a : Array(custom_fields).map { |item| field_pair(item) }
    pairs.each_with_object({}) do |(id, value), memo|
      field = ZendeskCompat::Config.ticket_field(id)
      next if field.nil? || field['system']

      key = attribute_key(field)
      memo[key] = from_zendesk(field, value) if key
    end
  end

  def attribute_key(field)
    definitions[field['id'].to_s] || field['key']
  end

  # Valor do campo pelo id (para a busca custom_field_<id>:valor).
  def search_value(field_id, value)
    field = ZendeskCompat::Config.ticket_field(field_id)
    return [nil, nil] if field.nil?

    [attribute_key(field), from_zendesk(field, value)]
  end

  # Valor gravado no atributo -> valor do Zendesk (tag da opção, booleano ou texto).
  def zendesk_value(field, raw)
    return field['type'] == 'checkbox' ? false : nil if raw.nil? || raw == ''

    case field['type']
    when 'list' then ZendeskCompat::Config.option_tag(field, raw)
    when 'checkbox' then ActiveModel::Type::Boolean.new.cast(raw) || false
    else raw.is_a?(String) ? raw : raw.to_s
    end
  end

  private

  def from_zendesk(field, value)
    return nil if value.nil? || value == '' || value == []

    case field['type']
    when 'list' then ZendeskCompat::Config.option_name(field, value) || value.to_s
    when 'checkbox' then ActiveModel::Type::Boolean.new.cast(value) ? true : nil
    when 'number' then numeric(value)
    else value.to_s
    end
  end

  def field_pair(item)
    item = item.to_h.with_indifferent_access
    [item[:id], item[:value]]
  end

  def numeric(value)
    Integer(value.to_s, 10)
  rescue ArgumentError
    Float(value.to_s, exception: false) || value.to_s
  end

  def definitions
    @definitions ||= @account.custom_attribute_definitions
                             .where(attribute_model: 'conversation_attribute')
                             .where('attribute_description LIKE ?', "#{FIELD_PREFIX}%")
                             .pluck(:attribute_description, :attribute_key).to_h
                             .transform_keys { |description| description.delete_prefix(FIELD_PREFIX).strip }
  end
end
# rubocop:enable Metrics/CyclomaticComplexity
