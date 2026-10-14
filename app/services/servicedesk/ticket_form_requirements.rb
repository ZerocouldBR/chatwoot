# Campos obrigatórios para resolver o ticket ("required to solve" do Zendesk), pelo formulário do ticket.
#
# Mesma regra do painel de propriedades (app/javascript/dashboard/servicedesk/ticketFormHelper.js):
#   - formulário efetivo = zd_formulario, se existir na configuração; senão o formulário padrão;
#   - um campo do formulário é obrigatório se estiver em required_field_ids ou se for filho obrigatório de uma
#     condição atendida (valor do campo pai igual ao da condição);
#   - campo condicional cuja condição não foi atendida não aparece, então não é exigido;
#   - campo inativo (nome com "(inativo)") vazio não aparece, então não é exigido.
# Fonte: os JSONs gerados do export (ticketForms.json e ticketFormsMeta.json), os mesmos do painel.
class Servicedesk::TicketFormRequirements
  CONFIG_DIR = Rails.root.join('app/javascript/dashboard/servicedesk')
  FIELD_PREFIX = 'zendesk_field:'.freeze
  FORM_KEY = 'zd_formulario'.freeze
  HEADER_KEYS = %w[zd_formulario zd_status zd_tipo zd_cc zd_seguidores].freeze
  INACTIVE = /\(inativo( no zendesk)?\)/i

  class << self
    def forms
      @forms ||= JSON.parse(File.read(CONFIG_DIR.join('ticketForms.json')))
    end

    def meta
      @meta ||= JSON.parse(File.read(CONFIG_DIR.join('ticketFormsMeta.json')))
    end
  end

  def initialize(conversation)
    @conversation = conversation
    @values = conversation.custom_attributes || {}
  end

  def form_name
    value = @values[FORM_KEY]
    value.present? && self.class.forms.key?(value) ? value : self.class.meta['default_form']
  end

  # [{ key:, name: }] dos campos obrigatórios vazios, na ordem do formulário
  def missing
    by_field = definitions_by_field_id
    Array(self.class.forms[form_name]).filter_map do |raw_id|
      definition = by_field[raw_id.to_s]
      next if definition.nil? || HEADER_KEYS.include?(definition.attribute_key)
      next if filled?(@values[definition.attribute_key])
      next unless required_and_visible?(raw_id.to_s, definition, by_field)

      { key: definition.attribute_key, name: definition.attribute_display_name }
    end
  end

  private

  def definitions_by_field_id
    @conversation.account.custom_attribute_definitions.conversation_attribute.each_with_object({}) do |definition, map|
      description = definition.attribute_description.to_s.strip
      next unless description.start_with?(FIELD_PREFIX)

      map[description.delete_prefix(FIELD_PREFIX).strip] = definition
    end
  end

  def required_and_visible?(field_id, definition, by_field)
    return false if definition.attribute_display_name.to_s.match?(INACTIVE)

    rules = child_rules[field_id] || []
    matched = matched_rules(rules, by_field)
    return false if rules.any? && matched.empty?

    required_ids.include?(field_id) || matched.any? { |rule| rule[:required] }
  end

  # Condições atendidas: o campo pai tem o valor da condição
  def matched_rules(rules, by_field)
    rules.select { |rule| parent_value(rule[:parent_id], by_field) == rule[:value] }
  end

  def parent_value(parent_id, by_field)
    definition = by_field[parent_id]
    definition && @values[definition.attribute_key]
  end

  def required_ids
    @required_ids ||= Array(self.class.meta['required_field_ids']).map(&:to_s)
  end

  def child_rules
    @child_rules ||= Array((self.class.meta['conditions'] || {})[form_name]).each_with_object({}) do |condition, map|
      Array(condition['child_fields']).each do |child|
        (map[child['id'].to_s] ||= []) << {
          parent_id: condition['parent_field_id'].to_s, value: condition['value'], required: child['is_required'] == true
        }
      end
    end
  end

  def filled?(value)
    !value.nil? && value.to_s.strip != ''
  end
end
