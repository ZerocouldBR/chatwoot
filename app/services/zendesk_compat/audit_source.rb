# De onde vêm as alterações registradas de um ticket, conforme o modelo de ticket do fork (ZendeskCompat::TicketModel):
#   Legacy: sd_ticket_audits (Servicedesk::TicketAuditTrail), já com os eventos no formato do Zendesk
#   Native: conversation_events (TicketAuditable do modelo f10), um registro por campo, agrupados por momento/autor/origem
#           e traduzidos para os nomes e valores do Zendesk (team_id -> group_id, ticket_type -> type, enum -> status...)
# Cada linha: { id:, created_at:, author:, via:, events: [{ 'type', 'field_name', 'value', 'previous_value' }] }.
module ZendeskCompat::AuditSource
  def self.for(conversation)
    ZendeskCompat::TicketModel.native? ? Native.new(conversation) : Legacy.new(conversation)
  end
end
