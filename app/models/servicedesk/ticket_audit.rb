# Histórico de alterações de um ticket (conversa) no formato dos audits do Zendesk (M7).
# Gravado por Servicedesk::TicketAuditTrail; lido por ZendeskCompat::AuditsBuilder.
class Servicedesk::TicketAudit < ApplicationRecord
  self.table_name = 'sd_ticket_audits'

  belongs_to :account
  belongs_to :conversation
  belongs_to :author, polymorphic: true, optional: true

  validates :via, presence: true
  validate :events_is_array

  private

  def events_is_array
    errors.add(:events, 'must be an array') unless events.is_a?(Array)
  end
end
