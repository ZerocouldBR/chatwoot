# Status de ticket do ServiceDesk (rótulo em `zd_status` + status nativo canônico).
# Fonte de verdade: config/servicedesk/ticket_statuses.yml (documentado no próprio arquivo).
class Servicedesk::TicketStatuses
  CONFIG_PATH = Rails.root.join('config/servicedesk/ticket_statuses.yml')
  # Enum de status do ticket da v3 (modelo do Victor). `pending` fica de fora de propósito: é a fila do bot/IA.
  NATIVE_STATUSES = %w[new_ticket open waiting_on_customer on_hold resolved closed].freeze
  # Como no Zendesk, macros e automações não levam o ticket para Novo nem para Fechado.
  NOT_SETTABLE_BY_ACTIONS = %w[new_ticket closed].freeze

  class << self
    def attribute_key
      config['attribute_key']
    end

    def statuses
      config['statuses']
    end

    def labels(active_only: false)
      list = active_only ? statuses.select { |status| status['active'] } : statuses
      list.pluck('label')
    end

    # Rótulo exato; na falta, compara sem acento e sem diferença de caixa.
    def find(label)
      return if label.blank?

      statuses.find { |status| status['label'] == label.to_s } ||
        statuses.find { |status| normalize(status['label']) == normalize(label) }
    end

    def category_for(label)
      find(label)&.fetch('category')
    end

    def native_status_for(label)
      category = category_for(label)
      category && config['categories'][category]
    end

    def reload!
      @config = nil
      config
    end

    private

    def config
      @config ||= load_config
    end

    def load_config
      data = YAML.safe_load_file(CONFIG_PATH)
      categories = data.fetch('categories')
      invalid = categories.reject { |_category, native| NATIVE_STATUSES.include?(native) }
      raise ArgumentError, "ticket_statuses.yml: status nativo fora do canônico #{invalid}" if invalid.any?

      statuses = data.fetch('statuses').map { |status| status.transform_keys(&:to_s).freeze }
      unknown = statuses.reject { |status| categories.key?(status['category']) }
      raise ArgumentError, "ticket_statuses.yml: categoria desconhecida em #{unknown.pluck('label')}" if unknown.any?

      { 'attribute_key' => data.fetch('attribute_key'), 'categories' => categories.freeze, 'statuses' => statuses.freeze }.freeze
    end

    def normalize(value)
      I18n.transliterate(value.to_s).squish.downcase
    end
  end
end
