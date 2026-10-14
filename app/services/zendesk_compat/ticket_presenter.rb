# Conversa -> ticket no formato do Zendesk (GET /api/v2/tickets/:id). Mapeamento em docs/IMPORTACAO.md (seção 4.1).
# rubocop:disable Metrics/AbcSize, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
class ZendeskCompat::TicketPresenter
  PRIORITIES = { 'low' => 'low', 'medium' => 'normal', 'high' => 'high', 'urgent' => 'urgent' }.freeze
  CHANNEL_BY_TYPE = {
    'Channel::Email' => 'email', 'Channel::Whatsapp' => 'whatsapp', 'Channel::WebWidget' => 'native_messaging',
    'Channel::Api' => 'api', 'Channel::Sms' => 'sms', 'Channel::TwilioSms' => 'sms', 'Channel::FacebookPage' => 'facebook',
    'Channel::Instagram' => 'instagram_dm', 'Channel::Telegram' => 'telegram', 'Channel::Line' => 'line', 'Channel::Voice' => 'voice'
  }.freeze
  MESSAGING_CHANNELS = %w[whatsapp native_messaging facebook instagram_dm telegram line sms chat].freeze

  def initialize(context)
    @context = context
  end

  def present(conversation)
    attrs = conversation.custom_attributes || {}
    ids = people_ids(conversation)
    fields = @context.fields.custom_fields(conversation)
    channel = channel(conversation)
    identity(conversation, attrs).merge(ids).merge(
      via: via(conversation, channel), status: ZendeskCompat::StatusTranslator.category(conversation),
      custom_status_id: ZendeskCompat::StatusTranslator.custom_status_id(conversation), priority: PRIORITIES[conversation.priority],
      type: ZendeskCompat::TicketModel.ticket_type(conversation),
      tags: conversation.label_list.sort, custom_fields: fields, fields: fields, recipient: recipient(conversation),
      from_messaging_channel: MESSAGING_CHANNELS.include?(channel), satisfaction_rating: satisfaction(attrs)
    )
  end

  def channel(conversation)
    original = conversation.additional_attributes&.dig('zendesk', 'via')
    return original['channel'] if original.is_a?(Hash) && original['channel'].present?

    label = (conversation.custom_attributes || {})['zd_canal']
    by_label = ZendeskCompat::Config.via_channels.key(label) if label.present?
    by_label || CHANNEL_BY_TYPE.fetch(conversation.inbox&.channel_type.to_s, 'api')
  end

  private

  def identity(conversation, attrs)
    subject = ZendeskCompat::TicketModel.subject(conversation)
    {
      url: @context.api_url("tickets/#{conversation.display_id}.json"), id: conversation.display_id,
      external_id: attrs['zd_id_externo'], created_at: @context.time(conversation.created_at),
      updated_at: @context.time(conversation.updated_at), generated_timestamp: conversation.updated_at.to_i,
      subject: subject, raw_subject: conversation.additional_attributes&.dig('zendesk', 'raw_subject') || subject,
      description: description(conversation), problem_id: ZendeskCompat::Ids.integer(attrs['zd_problema_id']),
      has_incidents: attrs['zd_incidentes'].present?, is_public: attrs['zd_publico'] != false,
      due_at: ZendeskCompat::TicketModel.due_at(conversation),
      forum_topic_id: nil, sharing_agreement_ids: [], followup_ids: [], brand_id: nil, allow_channelback: false,
      allow_attachments: true, ticket_form_id: form_id(attrs['zd_formulario']), encoded_id: attrs['zd_encoded_id']
    }
  end

  def people_ids(conversation)
    requester_id = ZendeskCompat::Ids.contact_id(conversation.contact) if conversation.contact
    submitter = ZendeskCompat::TicketModel.submitter(conversation)
    email_cc_ids = cc_emails(conversation).filter_map { |email| @context.directory.actor_by_email(email) }.map { |a| ZendeskCompat::Ids.user_id(a) }
    follower_ids = conversation.conversation_participants.includes(:user).filter_map { |p| p.user && ZendeskCompat::Ids.user_id(p.user) }
    {
      requester_id: requester_id, submitter_id: submitter ? ZendeskCompat::Ids.user_id(submitter) : requester_id,
      assignee_id: assignee_id(conversation),
      organization_id: organization_id(conversation), group_id: @context.directory.group_id(conversation.team),
      email_cc_ids: email_cc_ids.uniq, follower_ids: follower_ids.uniq, collaborator_ids: (email_cc_ids + follower_ids).uniq
    }
  end

  def assignee_id(conversation)
    return ZendeskCompat::Ids.user_id(conversation.assignee) if conversation.assignee

    bot = conversation.ai_assignee if conversation.respond_to?(:ai_assignee)
    bot.is_a?(AgentBot) ? ZendeskCompat::Ids.user_id(bot) : nil
  end

  def organization_id(conversation)
    ZendeskCompat::Ids.organization_id(ZendeskCompat::TicketModel.company(conversation, @context)) ||
      ZendeskCompat::Ids.integer(conversation.additional_attributes&.dig('zendesk', 'organization_id'))
  end

  def via(conversation, channel)
    original = conversation.additional_attributes&.dig('zendesk', 'via')
    return original if original.is_a?(Hash) && original['channel'].present?

    from = { address: conversation.contact&.email, name: conversation.contact&.name }.compact
    from[:phone] = conversation.contact.phone_number if conversation.contact&.phone_number.present?
    to = channel == 'email' ? { address: recipient(conversation), name: conversation.inbox&.name } : {}
    { channel: channel, source: { from: from, to: to.compact, rel: nil } }
  end

  def recipient(conversation)
    attrs = conversation.custom_attributes || {}
    channel = conversation.inbox&.channel
    inbox_email = channel.email if channel.respond_to?(:email)
    attrs['zd_destinatario'].presence || inbox_email
  end

  def description(conversation)
    first = conversation.messages.where(message_type: ZendeskCompat::CommentPresenter::COMMENT_TYPES).order(:created_at, :id).first
    first&.content.to_s
  end

  def cc_emails(conversation)
    ZendeskCompat::TicketModel.cc_emails(conversation)
  end

  def form_id(name)
    return if name.blank?

    ZendeskCompat::Config.data.fetch('forms', {})[name]
  end

  def satisfaction(attrs)
    score = attrs['zd_satisfacao']
    return { score: 'unoffered' } if score.blank?

    { score: score.to_s.downcase.include?('ruim') || score.to_s.downcase == 'bad' ? 'bad' : 'good', comment: attrs['zd_satisfacao_comentario'] }
  end
end
# rubocop:enable Metrics/AbcSize, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
