# ServiceDesk: trava "envio externo bloqueado" (ver Servicedesk::OutboundGuard).
Rails.application.config.to_prepare do
  ActionMailer::Base.register_interceptor(Servicedesk::OutboundGuard::MailInterceptor)
  unless ActionMailer::MessageDelivery < Servicedesk::OutboundGuard::MessageDeliveryGuard
    ActionMailer::MessageDelivery.prepend(Servicedesk::OutboundGuard::MessageDeliveryGuard)
  end
end

Rails.application.config.after_initialize do
  Rails.logger.info('[outbound-guard] SD_OUTBOUND_BLOCKED ligado: nenhum envio externo') if Servicedesk::OutboundGuard.globally_blocked?
end
