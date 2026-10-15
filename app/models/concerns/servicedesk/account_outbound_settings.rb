# Trava "envio externo bloqueado" da conta (Servicedesk::OutboundGuard). Valor efetivo = ENV SD_OUTBOUND_BLOCKED
# (todas as contas) ou settings.outbound_blocked da conta. Sem setter pela API de configurações da conta.
module Servicedesk::AccountOutboundSettings
  extend ActiveSupport::Concern

  included do
    store_accessor :settings, :outbound_blocked
    validates :outbound_blocked, inclusion: { in: [true, false] }, allow_nil: true
  end

  def servicedesk_outbound_blocked?
    Servicedesk::OutboundGuard.blocked?(self)
  end
end
