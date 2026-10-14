# ServiceDesk (M7): histórico de alterações do ticket (sd_ticket_audits) sem editar o model do upstream.
Rails.application.config.to_prepare do
  Conversation.include(Servicedesk::TicketAuditTrail) unless Conversation.include?(Servicedesk::TicketAuditTrail)
end
