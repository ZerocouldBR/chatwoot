# ServiceDesk (M7): histórico de alterações do ticket (sd_ticket_audits) sem editar o model do upstream.
# Com o modelo de ticket nativo (feat/tickets-f2-audit: TicketAuditable/conversation_events) o histórico já existe e este
# concern não é incluído: a API de compatibilidade lê conversation_events (ZendeskCompat::AuditSource).
Rails.application.config.to_prepare do
  native_trail = Object.const_defined?(:TicketAuditable) && Conversation.include?(TicketAuditable)
  Conversation.include(Servicedesk::TicketAuditTrail) unless native_trail || Conversation.include?(Servicedesk::TicketAuditTrail)
end
