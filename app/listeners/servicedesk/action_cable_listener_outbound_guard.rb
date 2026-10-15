# Trava "envio externo bloqueado" (Servicedesk::OutboundGuard) no tempo real: numa conta isolada os eventos vão só
# para os agentes; o cliente (widget, API do cliente) não recebe nada.
module Servicedesk::ActionCableListenerOutboundGuard
  private

  def contact_inbox_tokens(contact_inbox)
    return [] if Servicedesk::OutboundGuard.blocked?(contact_inbox.inbox&.account)

    super
  end

  def typing_event_listener_tokens(account, conversation, user)
    tokens = super
    return tokens unless Servicedesk::OutboundGuard.blocked?(account)

    tokens - [conversation.contact_inbox&.pubsub_token]
  end
end
