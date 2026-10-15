# Grava em sd_ticket_audits cada mudança de status, responsável, time, prioridade, etiquetas e campos do ticket,
# com o autor (Current.user) e a origem (api/regra/painel), como os audits do Zendesk (M7).
# Incluído em Conversation pelo config/initializers/servicedesk_ticket_audits.rb (sem editar o model do upstream).
# Uma falha aqui nunca interrompe a atualização da conversa.
module Servicedesk::TicketAuditTrail
  extend ActiveSupport::Concern

  TRACKED_KEYS = %w[status assignee_id assignee_agent_bot_id team_id priority custom_attributes cached_label_list].freeze

  included do
    after_commit :sd_record_ticket_audit, on: :update
  end

  private

  def sd_record_ticket_audit
    changes = saved_changes.slice(*TRACKED_KEYS)
    return if changes.empty?

    events = Servicedesk::TicketAuditEvents.new(self, changes).build
    return if events.empty?

    Servicedesk::TicketAudit.create!(account_id: account_id, conversation_id: id, author: sd_audit_author, via: sd_audit_via_label,
                                     events: events, created_at: Time.current)
  rescue StandardError => e
    Rails.logger.warn({ event: 'sd_ticket_audit_failed', conversation_id: id, error: e.class.name, message: e.message }.to_json)
  end

  def sd_audit_author
    actor = Current.user
    actor if actor.is_a?(User) || actor.is_a?(AgentBot)
  end

  def sd_audit_via_label
    return Servicedesk::TicketAuditContext.via if Servicedesk::TicketAuditContext.via.present?
    return 'rule' if Current.executed_by.present? && !Current.executed_by.is_a?(User)

    Current.user.present? ? 'web' : 'system'
  end
end
