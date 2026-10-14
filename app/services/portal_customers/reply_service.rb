# ServiceDesk B2B: resposta do cliente pelo portal (comentário público + anexos) e "Marcar como resolvido".
# - Ticket aberto, pendente ou em espera: a mensagem do cliente volta o ticket para Aberto (regra do Message).
# - Ticket resolvido: a mensagem reabre o ticket, como no e-mail (Message#reopen_conversation).
# - Ticket fechado: não aceita mensagens; a resposta abre um ticket de acompanhamento ligado ao fechado
#   (Tickets::FollowupBuilder, o mesmo do e-mail), como o "Criar acompanhamento" do Zendesk.
# #perform devolve o ticket que recebeu a mensagem (o próprio ou o acompanhamento).
class PortalCustomers::ReplyService
  MAX_CONTENT = 20_000

  pattr_initialize [:conversation!, :contact!, :content, { attachments: [], solve: false }]

  def perform
    validate!(text, uploads)

    as_contact do
      target = conversation.closed? ? create_followup! : conversation
      create_message(target, text, uploads) if text.present? || uploads.any?
      # depois do commit da mensagem: a mensagem do cliente reabre o ticket, então resolve por último
      resolve!(target) if resolve_requested?(target)
      target
    end
  end

  private

  # Autor da auditoria (conversation_events, via "customer"): o contato do portal, só durante a operação.
  def as_contact
    previous = Current.contact
    Current.contact = contact
    yield
  ensure
    Current.contact = previous
  end

  def uploads
    @uploads ||= Array(attachments).compact_blank.select { |file| file.respond_to?(:content_type) }
  end

  def text
    @text ||= content.to_s.strip.first(MAX_CONTENT)
  end

  def resolve_requested?(target)
    solve && !conversation.closed? && !target.reload.resolved?
  end

  def validate!(text, uploads)
    if uploads.size > PortalCustomers::CreateRequestService::MAX_ATTACHMENTS
      raise PortalCustomers::CreateRequestService::Error,
            I18n.t('public_portal.sd.requests.errors.too_many_attachments', count: PortalCustomers::CreateRequestService::MAX_ATTACHMENTS)
    end
    return if text.present? || uploads.any?
    return if solve && !conversation.closed?

    raise PortalCustomers::CreateRequestService::Error, I18n.t('public_portal.sd.requests.errors.reply_required')
  end

  # O acompanhamento só é gravado junto com a mensagem: sem mensagem válida, nada fica criado.
  def create_followup!
    followup = Tickets::FollowupBuilder.new(
      source: conversation,
      additional_attributes: { 'source' => 'help_center', 'portal_slug' => conversation.additional_attributes&.dig('portal_slug'),
                               'mail_subject' => conversation.subject }.compact
    ).build
    followup.custom_attributes = (conversation.custom_attributes || {}).slice('zd_formulario')
                                                                       .merge('zd_canal' => 'Central de Ajuda', 'zd_status' => 'Novo',
                                                                              'zd_status_sistema' => 'Novo')
    followup
  end

  def create_message(target, text, uploads)
    ActiveRecord::Base.transaction do
      target.save! if target.new_record?
      message = target.messages.new(account_id: target.account_id, inbox_id: target.inbox_id, sender: contact,
                                    message_type: :incoming, content: text.presence)
      PortalCustomers::AttachmentBuilder.new(message: message, uploads: uploads).build
      message.save!
    end
  rescue ActiveRecord::RecordInvalid => e
    raise PortalCustomers::CreateRequestService::Error, PortalCustomers::AttachmentBuilder.error_messages(e.record)
  end

  def resolve!(target)
    target.custom_attributes = (target.custom_attributes || {}).merge('zd_status' => 'Resolvido', 'zd_status_sistema' => 'Resolvido')
    target.update!(status: :resolved)
  end
end
