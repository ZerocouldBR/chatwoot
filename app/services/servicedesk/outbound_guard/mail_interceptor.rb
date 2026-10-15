# Última barreira dos e-mails (ActionMailer interceptor): com a ENV ligada nenhum e-mail sai; sem ela, sai só o que
# não é de conta isolada. A conta vem do cabeçalho interno X-SD-Account-Id, posto pelo ApplicationMailer e
# retirado aqui (nunca chega ao destinatário).
class Servicedesk::OutboundGuard::MailInterceptor
  def self.delivering_email(message)
    header = message.header[Servicedesk::OutboundGuard::ACCOUNT_HEADER]
    account_id = header&.value
    message.header[Servicedesk::OutboundGuard::ACCOUNT_HEADER] = nil if header
    return unless Servicedesk::OutboundGuard.globally_blocked? || Servicedesk::OutboundGuard.blocked?(account_id.presence)

    message.perform_deliveries = false
    Servicedesk::OutboundGuard.log('email', account_id)
  end
end
