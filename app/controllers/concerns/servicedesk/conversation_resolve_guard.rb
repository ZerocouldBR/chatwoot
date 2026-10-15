# Bloqueia "Resolver" pela API enquanto faltar campo obrigatório do formulário do ticket (M1, required to solve).
# Cobre os dois caminhos de resolver da interface do Victor:
#   - toggle_status (botão Resolver, menu de status, barra de comandos): status=resolved ou o toggle sem status;
#   - "Enviar como Resolvido" (resposta + status na mesma requisição): messages#create com ticket_status=resolved.
# Vale só para usuários humanos (bots e regras seguem como no Chatwoot) e é desligado por padrão
# (configuração da conta `servicedesk_require_form_on_resolve`, ENV SD_REQUIRE_FORM_ON_RESOLVE).
module Servicedesk::ConversationResolveGuard
  extend ActiveSupport::Concern

  private

  def servicedesk_require_form_on_resolve
    return unless Current.user.is_a?(User) && Current.account.servicedesk_require_form_on_resolve?
    return unless servicedesk_resolving?

    missing = ::Servicedesk::TicketFormRequirements.new(servicedesk_guarded_conversation).missing
    return if missing.empty?

    render json: {
      error: I18n.t('errors.servicedesk.required_form_fields', fields: missing.pluck(:name).join(', ')),
      missing_attributes: missing
    }, status: :unprocessable_entity
  end

  def servicedesk_guarded_conversation
    @conversation || conversation
  end

  # Cada controller diz qual status está sendo pedido; nil = troca sem status explícito (toggle do Chatwoot).
  def servicedesk_resolving?
    requested = servicedesk_requested_status
    return requested == 'resolved' if requested.present?

    servicedesk_toggle_without_status? && servicedesk_guarded_conversation.open?
  end

  def servicedesk_toggle_without_status?
    false
  end
end
