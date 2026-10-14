# Configuração do ServiceDesk na conta (integ/final-v3, sobre a interface do Victor).
#
#   servicedesk_require_form_on_resolve  bloqueia "Resolver" (e "Enviar como Resolvido") enquanto faltar campo
#                                        obrigatório do formulário do ticket (required to solve do Zendesk, M1),
#                                        no painel e na API.
#
# Sem valor na conta, vale o padrão da instalação: ENV SD_REQUIRE_FORM_ON_RESOLVE (padrão false, desligado).
module Servicedesk::AccountAgentUiSettings
  extend ActiveSupport::Concern

  AGENT_UI_SETTINGS = {
    servicedesk_require_form_on_resolve: 'SD_REQUIRE_FORM_ON_RESOLVE'
  }.freeze

  included do
    store_accessor :settings, *AGENT_UI_SETTINGS.keys
    before_validation :normalize_servicedesk_agent_ui_settings
    AGENT_UI_SETTINGS.each_key do |key|
      validates key, inclusion: { in: [true, false] }, allow_nil: true
    end
  end

  class_methods do
    def servicedesk_setting_default(key)
      env = AGENT_UI_SETTINGS.fetch(key.to_sym)
      ActiveModel::Type::Boolean.new.cast(ENV.fetch(env, 'false')) == true
    end
  end

  def servicedesk_require_form_on_resolve?
    value = servicedesk_require_form_on_resolve
    return self.class.servicedesk_setting_default(:servicedesk_require_form_on_resolve) if value.nil?

    value == true
  end

  private

  # A API pode mandar "true"/"false" (form) em vez de booleano.
  def normalize_servicedesk_agent_ui_settings
    AGENT_UI_SETTINGS.each_key do |key|
      case public_send(key).to_s
      when 'true', '1' then public_send("#{key}=", true)
      when 'false', '0' then public_send("#{key}=", false)
      when '' then public_send("#{key}=", nil)
      end
    end
  end
end
