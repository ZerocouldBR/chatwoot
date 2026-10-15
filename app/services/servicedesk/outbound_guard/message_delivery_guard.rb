# Não enfileira e-mail (deliver_later) de conta isolada: nem o job de envio é criado. A conta vem dos params do
# mailer (with(account:)) ou dos argumentos (conta, conversa, mensagem, notificação...). O deliver_now segue até o
# interceptor, que bloqueia a entrega e mantém o retorno que o chamador espera.
#
# ActionMailer::MessageDelivery é um Delegator (BasicObject): qualquer método que ele não conheça processa o e-mail,
# e aí o deliver_later recusa. Por isso aqui só há variáveis de instância e constantes absolutas.
module Servicedesk::OutboundGuard::MessageDeliveryGuard
  def deliver_later(...)
    return super unless servicedesk_outbound_blocked?

    ::Servicedesk::OutboundGuard.log("email #{@mailer_class}##{@action}", servicedesk_outbound_account)
  end

  def deliver_later!(...)
    return super unless servicedesk_outbound_blocked?

    ::Servicedesk::OutboundGuard.log("email #{@mailer_class}##{@action}", servicedesk_outbound_account)
  end

  private

  def servicedesk_outbound_blocked?
    ::Servicedesk::OutboundGuard.globally_blocked? || ::Servicedesk::OutboundGuard.account_blocked?(servicedesk_outbound_account)
  end

  def servicedesk_outbound_account
    @servicedesk_outbound_account ||= servicedesk_outbound_candidates.lazy.filter_map { |candidate| servicedesk_account_of(candidate) }.first
  end

  def servicedesk_outbound_candidates
    params = @params.is_a?(::Hash) ? @params : {}
    args = @args.is_a?(::Array) ? @args : []
    [params[:account], *params.values, *args]
  end

  def servicedesk_account_of(candidate)
    return candidate if candidate.is_a?(::Account)
    return unless candidate.is_a?(::ActiveRecord::Base) && candidate.respond_to?(:account)

    candidate.account
  rescue ::StandardError
    nil
  end
end
