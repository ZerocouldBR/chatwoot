# Estrutura da conta Zendesk que a camada de compatibilidade (M7) precisa para traduzir os dados:
# campos de ticket (tipo e opções tag -> nome), grupos, canais, prioridades, tipos e status personalizados.
# Fonte: config/servicedesk/zendesk_compat.json, gerado por script/servicedesk_zendesk_compat_config.py.
# O vínculo campo -> atributo vale primeiro pelo banco (descrição "zendesk_field:<id>" da definição do atributo).
# rubocop:disable Metrics/CyclomaticComplexity
class ZendeskCompat::Config
  PATH = Rails.root.join('config/servicedesk/zendesk_compat.json')

  class << self
    def data
      @data ||= JSON.parse(File.read(PATH)).freeze
    end

    def reload!
      @data = nil
      @fields_by_id = nil
      data
    end

    def ticket_fields
      data['ticket_fields']
    end

    def ticket_field(id)
      fields_by_id[id.to_i]
    end

    def custom_ticket_fields
      ticket_fields.reject { |field| field['system'] }
    end

    # tag do Zendesk -> nome da opção (o que fica gravado no atributo de lista)
    def option_name(field, tag)
      return if tag.nil?

      pair = all_options(field).find { |option_tag, _name| option_tag == tag.to_s }
      pair&.last
    end

    # nome da opção gravado no atributo -> tag do Zendesk; aceita a própria tag
    def option_tag(field, name)
      return if name.nil?

      options = all_options(field)
      by_name = options.find { |_tag, option_name| option_name == name.to_s } ||
                options.find { |_tag, option_name| normalize(option_name) == normalize(name) }
      return by_name.first if by_name
      return name.to_s if options.any? { |tag, _name| tag == name.to_s }

      fallback_tag(name)
    end

    def groups
      data['groups']
    end

    def via_channels
      data['via_channels']
    end

    def priorities
      data['priorities']
    end

    def types
      data['types']
    end

    def custom_statuses
      data['custom_statuses']
    end

    def user_fields
      data['user_fields']
    end

    def normalize(value)
      I18n.transliterate(value.to_s).squish.downcase
    end

    private

    def fields_by_id
      @fields_by_id ||= ticket_fields.index_by { |field| field['id'].to_i }
    end

    def all_options(field)
      Array(field && field['options']) + Array(field && field['historical_options'])
    end

    def fallback_tag(name)
      name.to_s.strip.downcase.gsub(/\s+/, '_')
    end
  end
end
# rubocop:enable Metrics/CyclomaticComplexity
