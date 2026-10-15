# Trava "envio externo bloqueado" (Servicedesk::OutboundGuard) nas mensagens: a resposta pública ou o modelo (CSAT...)
# de uma conta isolada é gravado no ticket já marcado como não enviado (status failed + external_error, que o painel
# mostra na mensagem) e o envio pelo canal nem é enfileirado; o bloqueio vai para a auditoria do ticket.
module Servicedesk::MessageOutboundGuard
  extend ActiveSupport::Concern

  included do
    before_create :mark_outbound_blocked, if: :outbound_guard_applies?
  end

  def outbound_blocked?
    Servicedesk::OutboundGuard.blocked_message?(self)
  end

  private

  def outbound_guard_applies?
    Servicedesk::OutboundGuard.outbound_message?(self) && Servicedesk::OutboundGuard.blocked?(account)
  end

  def mark_outbound_blocked
    self.status = :failed
    self.content_attributes = (content_attributes || {}).merge(
      Servicedesk::OutboundGuard::MESSAGE_FLAG => true, 'external_error' => Servicedesk::OutboundGuard.not_sent_reason(account)
    )
  end

  # Chamado no lugar do envio (send_reply): true quando a conta está isolada.
  def outbound_guard_skip_reply?
    return false unless outbound_blocked? || Servicedesk::OutboundGuard.blocked?(account)

    if outbound_blocked?
      Servicedesk::OutboundGuard.log("message #{inbox&.channel_type}", account_id)
      Servicedesk::OutboundGuard.record(conversation, 'message', { 'message_id' => id, 'channel' => inbox&.channel_type })
    else
      Servicedesk::OutboundGuard.block_message!(self)
    end
    true
  end
end
