# Alterações gravadas em sd_ticket_audits (modelo legado), já no formato do Zendesk.
class ZendeskCompat::AuditSource::Legacy
  def initialize(conversation)
    @conversation = conversation
  end

  def rows(after_id: nil)
    scope = Servicedesk::TicketAudit.where(conversation_id: @conversation.id).includes(:author).order(:id)
    scope = scope.where('id > ?', after_id.to_i) if after_id
    scope.map { |audit| { id: audit.id, created_at: audit.created_at, author: audit.author, via: audit.via, events: audit.events } }
  end

  def last_id
    Servicedesk::TicketAudit.where(conversation_id: @conversation.id).maximum(:id)
  end

  # O modelo legado não grava a criação: o AuditsBuilder monta o Create.
  def create_values
    nil
  end
end
