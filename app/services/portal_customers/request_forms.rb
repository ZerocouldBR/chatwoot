# ServiceDesk B2B: formulários de "Enviar uma solicitação".
#
# No Zendesk da B2B só um formulário é ativo e visível ao usuário final: "Atendimento" (21763507779611).
# Dos 17 campos dele, o cliente vê e edita só Assunto, Descrição e "CNPJ" (título no portal do campo
# "CNPJ o CUIT (Argentina)", 21583294863643, opcional). "Atribuído para" é só leitura e aparece no detalhe.
# Os demais (Área interna, Tabulação etc.) são internos.
#
# O portal pode sobrescrever a lista em config.customer_portal.request_forms (mesmo formato de DEFAULT_FORMS).
# Assunto e Descrição são fixos e sempre obrigatórios; `fields` são os campos extras.
class PortalCustomers::RequestForms
  DEFAULT_FORMS = [
    {
      'id' => 'atendimento',
      'name' => 'Atendimento',
      'zendesk_id' => 21_763_507_779_611,
      'fields' => [
        { 'key' => 'cnpj', 'label' => 'CNPJ', 'type' => 'text', 'required' => false,
          'attribute_key' => 'zd_cnpj_o_cuit_argentina' }
      ]
    }
  ].freeze

  MAX_FIELD_LENGTH = 1000

  Form = Struct.new(:id, :name, :description, :inbox_id, :zendesk_id, :fields, keyword_init: true)
  Field = Struct.new(:key, :label, :type, :required, :description, :attribute_key, :options, keyword_init: true)

  pattr_initialize [:portal!]

  def all
    raw = portal.customer_portal['request_forms']
    raw = DEFAULT_FORMS if raw.blank?
    raw.map { |form| build_form(form) }
  end

  def find(id)
    forms = all
    forms.find { |form| form.id == id.to_s } || forms.first
  end

  def inbox_for(form)
    inbox_id = form.inbox_id.presence || portal.customer_portal['request_inbox_id']
    portal.account.inboxes.find_by(id: inbox_id) if inbox_id.present?
  end

  # Valida os campos extras enviados e devolve [atributos_custom, erros].
  def extract_fields(form, values)
    values = values.respond_to?(:to_unsafe_h) ? values.to_unsafe_h : (values || {}).to_h
    attributes = {}
    errors = []
    form.fields.each do |field|
      value = values[field.key].to_s.strip
      errors << field.label unless field_value_valid?(field, value)
      attributes[self.class.attribute_key_for(field)] = value.first(MAX_FIELD_LENGTH) if value.present?
    end
    [attributes, errors.uniq]
  end

  def self.attribute_key_for(field)
    field.attribute_key.presence || "portal_#{field.key}"
  end

  private

  def field_value_valid?(field, value)
    return !field.required if value.blank?
    return field.options.include?(value) if field.type == 'list' && field.options.present?
    return value.match?(/\A-?\d+([.,]\d+)?\z/) if field.type == 'number'

    true
  end

  def build_form(form)
    form = form.to_h.stringify_keys
    Form.new(
      id: form['id'].to_s, name: form['name'].to_s, description: form['description'],
      inbox_id: form['inbox_id'], zendesk_id: form['zendesk_id'],
      fields: Array(form['fields']).map { |field| build_field(field.to_h.stringify_keys) }
    )
  end

  def build_field(field)
    Field.new(key: field['key'].to_s, label: field['label'].to_s, type: field['type'].presence || 'text',
              required: field['required'] == true, description: field['description'], attribute_key: field['attribute_key'],
              options: Array(field['options']).map(&:to_s))
  end
end
