# Extensões do ServiceDesk na Account, num include só (mantém o Account dentro do Metrics/ClassLength):
# - AccountMacroSettings: macro_fill_editor (M5.1, a macro preenche o editor);
# - AccountRoles: papéis do Zendesk (sd_roles) semeados na criação da conta (M13);
# - AccountAgentUiSettings: formulário obrigatório ao resolver (M1);
# - AccountOutboundSettings: trava "envio externo bloqueado" (conta isolada).
module Servicedesk::AccountExtensions
  extend ActiveSupport::Concern

  included do
    include Servicedesk::AccountMacroSettings
    include Servicedesk::AccountRoles
    include Servicedesk::AccountAgentUiSettings
    include Servicedesk::AccountOutboundSettings
  end
end
