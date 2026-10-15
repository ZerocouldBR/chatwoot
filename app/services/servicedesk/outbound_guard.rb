# ServiceDesk: trava "envio externo bloqueado" (conta isolada).
#
# Com a trava ligada NADA sai da conta, venha de onde vier (regra, agente, macro, job ou integração):
# e-mails de qualquer mailer, mensagens pelos canais (e-mail, WhatsApp, API, SMS, Telegram...), CSAT, webhooks
# (da conta, da inbox de API, de bot, de regra e de macro), integrações (Slack, Dialogflow...), push/web push e o link
# mágico do portal. A mensagem continua gravada no ticket, marcada como não enviada, e o bloqueio vai para a
# auditoria do ticket (conversation_events, event_type "outbound_blocked"). As notificações internas do app seguem.
#
# Onde liga:
#   - ENV SD_OUTBOUND_BLOCKED=true  bloqueia TODAS as contas e todo e-mail da instalação (inclusive Devise);
#   - accounts.settings.outbound_blocked = true  bloqueia só aquela conta (gravado por script/console; a API de
#     configurações da conta não aceita essa chave, para que ninguém destrave pelo painel).
module Servicedesk::OutboundGuard
  ENV_KEY = 'SD_OUTBOUND_BLOCKED'.freeze
  SETTING_KEY = 'outbound_blocked'.freeze
  ACCOUNT_HEADER = 'X-SD-Account-Id'.freeze
  MESSAGE_FLAG = 'sd_outbound_blocked'.freeze
  EVENT_TYPE = 'outbound_blocked'.freeze

  module_function

  def globally_blocked?
    ActiveModel::Type::Boolean.new.cast(ENV.fetch(ENV_KEY, false)) == true
  end

  # account: Account, id, ou qualquer objeto com #account (conversa, mensagem, inbox, contato, hook...).
  def blocked?(account = nil)
    return true if globally_blocked?

    account_blocked?(resolve_account(account))
  end

  def account_blocked?(account)
    account.is_a?(Account) && ActiveModel::Type::Boolean.new.cast(account.settings&.[](SETTING_KEY)) == true
  end

  def resolve_account(object)
    case object
    when Account then object
    when Integer then Account.find_by(id: object)
    when String then object.match?(/\A\d+\z/) ? Account.find_by(id: object.to_i) : nil
    else object.respond_to?(:account) ? object.account : nil
    end
  end

  # Só log (sem dado pessoal): o canal e o id da conta.
  def log(channel, account = nil, detail = nil)
    account_id = account.respond_to?(:id) ? account.id : account
    Rails.logger.info("[outbound-guard] envio bloqueado: #{channel} conta=#{account_id || '-'}#{" #{detail}" if detail.present?}")
    nil
  end

  # Registra o bloqueio na auditoria do ticket, sem disparar gatilhos (não é uma atualização do ticket).
  def record(conversation, channel, value = {})
    return if conversation.blank?

    conversation.conversation_events.create!(account_id: conversation.account_id, event_type: EVENT_TYPE, via: 'system',
                                             field_name: channel.to_s, value: value, created_at: Time.current)
  rescue StandardError => e
    Rails.logger.warn("[outbound-guard] falha ao auditar o bloqueio: #{e.class}")
  end

  # Mensagens que iriam para fora pelo canal do ticket: respostas públicas e modelos (CSAT, formulários...).
  def outbound_message?(message)
    !message.private? && (message.outgoing? || message.template?)
  end

  def blocked_message?(message)
    message.content_attributes.is_a?(Hash) && message.content_attributes[MESSAGE_FLAG] == true
  end

  # Marca (sem callbacks) uma mensagem que iria para fora como não enviada e audita. Usado onde a mensagem já existe
  # (SendReplyJob, "tentar de novo"); a mensagem nova já nasce marcada (Servicedesk::MessageOutboundGuard).
  def block_message!(message)
    log("message #{message.inbox&.channel_type}", message.account_id)
    return unless outbound_message?(message)
    return if blocked_message?(message) && message.failed?

    attributes = (message.content_attributes || {}).merge(MESSAGE_FLAG => true, 'external_error' => not_sent_reason(message.account))
    message.update_columns(status: Message.statuses[:failed], content_attributes: attributes) # rubocop:disable Rails/SkipsModelValidations
    record(message.conversation, 'message', { 'message_id' => message.id, 'channel' => message.inbox&.channel_type })
  end

  def not_sent_reason(account = nil)
    I18n.with_locale(locale_for(account)) { I18n.t('servicedesk.outbound_guard.not_sent') }
  end

  def locale_for(account)
    locale = account.respond_to?(:locale) ? account.locale.to_s : ''
    I18n.available_locales.map(&:to_s).include?(locale) ? locale : I18n.default_locale
  end

  # Conta a partir do corpo de um webhook (account: { id: }, account_id, ou dentro de conversation/message).
  def account_id_from_payload(payload)
    return unless payload.is_a?(Hash)

    payload = payload.with_indifferent_access
    payload.dig(:account, :id) || payload[:account_id] || payload.dig(:conversation, :account_id) ||
      payload.dig(:message, :account_id) || payload.dig(:conversation, :account, :id)
  end
end
