# Ponto ÚNICO onde a API de compatibilidade lê e grava os campos de ticket que dependem do modelo de ticket do fork.
# Dois modelos, detectados pelo schema (sem configuração):
#   :legacy (servicedesk/main) - status nativo do Chatwoot + rótulo zd_status (decisão 1), assunto em mail_subject/zd_assunto,
#            tipo em zd_tipo, vencimento em zd_vencimento, CCs em zd_cc, histórico em sd_ticket_audits
#   :native (feat/tickets-f0..f10) - enum de status do Zendesk (new_ticket, open, waiting_on_customer, on_hold, resolved,
#            closed), colunas subject/ticket_type/due_at/company_id/submitter_id, conversation_ccs e conversation_events
# Para apontar a API para outro modelo de ticket, só este arquivo, ZendeskCompat::StatusTranslator e ZendeskCompat::AuditSource mudam.
module ZendeskCompat::TicketModel
  # categoria do Zendesk -> valor do enum de status do modelo nativo
  NATIVE_STATUS = { 'new' => 'new_ticket', 'open' => 'open', 'pending' => 'waiting_on_customer', 'hold' => 'on_hold',
                    'solved' => 'resolved', 'closed' => 'closed' }.freeze
  TICKET_TYPES = %w[question incident problem task].freeze

  module_function

  def native?
    return @native unless @native.nil?

    @native = Conversation.statuses.key?('new_ticket') && Conversation.column_names.include?('subject')
  end

  # Só para testes: força um modelo (nil = detectar de novo).
  def force!(value)
    @native = value
  end

  # Rótulos de status personalizado (zd_status, config/servicedesk/ticket_statuses.yml) existem neste fork?
  def labels?
    Object.const_defined?('Servicedesk::TicketStatuses')
  rescue NameError
    false
  end

  def attrs(conversation)
    conversation.custom_attributes || {}
  end

  def subject(conversation)
    native = conversation.subject.presence if native?
    native || conversation.additional_attributes&.dig('mail_subject').presence || attrs(conversation)['zd_assunto']
  end

  def assign_subject(conversation, value)
    text = value.to_s
    conversation.subject = text.truncate(150) if native?
    conversation.additional_attributes = (conversation.additional_attributes || {}).merge('mail_subject' => text)
    conversation.custom_attributes = attrs(conversation).merge('zd_assunto' => text) unless native?
  end

  # tipo do Zendesk (question/incident/problem/task)
  def ticket_type(conversation)
    return conversation.ticket_type if native?

    ZendeskCompat::Config.types.key(attrs(conversation)['zd_tipo'])
  end

  # nil = tipo inválido
  def assign_type(conversation, value)
    tag = value.to_s.presence
    return :invalid if tag && TICKET_TYPES.exclude?(tag)

    if native?
      conversation.ticket_type = tag
    else
      conversation.custom_attributes = attrs(conversation).merge('zd_tipo' => tag && ZendeskCompat::Config.types[tag]).compact
    end
  end

  def due_at(conversation)
    native? ? conversation.due_at&.utc&.iso8601 : attrs(conversation)['zd_vencimento']
  end

  def assign_due_at(conversation, value)
    if native?
      conversation.due_at = value.presence && Time.zone.parse(value.to_s)
    else
      conversation.custom_attributes = attrs(conversation).merge('zd_vencimento' => value.presence).compact
    end
  end

  def company(conversation, context)
    native = conversation.company if native?
    native || context.company(conversation.contact)
  end

  def submitter(conversation)
    native? ? conversation.submitter : nil
  end

  def cc_emails(conversation)
    return conversation.conversation_ccs.order(:id).pluck(:email) if native?

    ZendeskCompat::CcList.parse(attrs(conversation)[ZendeskCompat::CcList::ATTRIBUTE])
  end

  # Grava a lista final de CCs. No modelo nativo vira registros em conversation_ccs (chamar depois de salvar a conversa).
  def write_cc_emails(conversation, emails)
    list = ZendeskCompat::CcList.parse(emails)
    return write_native_ccs(conversation, list) if native?

    conversation.custom_attributes = attrs(conversation).merge(ZendeskCompat::CcList::ATTRIBUTE => ZendeskCompat::CcList.dump(list)).compact
  end

  def write_native_ccs(conversation, list)
    conversation.conversation_ccs.where.not(email: list).delete_all
    existing = conversation.conversation_ccs.pluck(:email)
    (list - existing).each { |email| conversation.conversation_ccs.create!(account_id: conversation.account_id, email: email) }
  end

  # O modelo nativo manda os CCs em toda resposta pública por conta própria; no legado a API passa cc_emails.
  def ccs_sent_by_mailer?
    native?
  end

  # Coluna de busca por texto livre (assunto).
  def subject_sql
    mail_subject = "conversations.additional_attributes->>'mail_subject'"
    native? ? "COALESCE(conversations.subject, #{mail_subject})" : mail_subject
  end

  def solved_statuses
    native? ? %w[resolved closed] : %w[resolved]
  end
end
