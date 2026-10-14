# Status do Zendesk <-> status do ticket no ServiceDesk, nos dois modelos (ZendeskCompat::TicketModel):
#   legado: rótulo em zd_status + status nativo do Chatwoot pela categoria (decisão 1); "closed" = zd_status_sistema Fechado;
#           sem rótulo, pelo status nativo (open -> open, pending -> new, snoozed -> pending, resolved -> solved)
#   nativo (f10): enum de status do Zendesk; o rótulo zd_status, se existir no fork, só refina o custom_status_id
# Escrita: status do Zendesk -> rótulo padrão da categoria (custom_statuses[].default) e custom_status_id -> rótulo exato,
# mais o status do modelo.
# rubocop:disable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity, Metrics/ModuleLength
module ZendeskCompat::StatusTranslator
  ORDER = %w[new open pending hold solved closed].freeze
  NATIVE_CATEGORY = { 'open' => 'open', 'pending' => 'new', 'snoozed' => 'pending', 'resolved' => 'solved' }.freeze
  ENUM_CATEGORY = { 'new_ticket' => 'new', 'open' => 'open', 'waiting_on_customer' => 'pending', 'on_hold' => 'hold',
                    'resolved' => 'solved', 'closed' => 'closed', 'pending' => 'new' }.freeze
  SYSTEM_LABELS = { 'closed' => 'Fechado', 'deleted' => 'Excluído' }.freeze
  SYSTEM_ATTRIBUTE = 'zd_status_sistema'.freeze
  LABEL_ATTRIBUTE = 'zd_status'.freeze

  module_function

  def category(conversation)
    return ENUM_CATEGORY.fetch(conversation.status.to_s, 'open') if ZendeskCompat::TicketModel.native?

    attributes = conversation.custom_attributes || {}
    system_label = attributes[SYSTEM_ATTRIBUTE]
    return 'closed' if system_label == SYSTEM_LABELS['closed'] && conversation.resolved?
    return 'deleted' if system_label == SYSTEM_LABELS['deleted']

    label = attributes[LABEL_ATTRIBUTE]
    status_category = label_category(label) if label.present?
    status_category = NATIVE_CATEGORY[conversation.status] if status_category.nil? || !consistent?(status_category, conversation)
    status_category || 'open'
  end

  # O rótulo pode ter ficado para trás se alguém mudou só o status nativo pelo painel padrão do Chatwoot.
  def consistent?(status_category, conversation)
    native = native_for_category(status_category)
    native.nil? || native == conversation.status || (conversation.pending? && status_category == 'new')
  end

  def native_for_category(status_category)
    return ZendeskCompat::TicketModel::NATIVE_STATUS[status_category] if ZendeskCompat::TicketModel.native?
    return unless labels?

    status = statuses.find { |entry| entry['category'] == status_category }
    status && Servicedesk::TicketStatuses.native_status_for(status['label'])
  end

  def custom_status_id(conversation)
    current = category(conversation)
    current = 'solved' if current == 'closed'
    label = (conversation.custom_attributes || {})[LABEL_ATTRIBUTE]
    status = find_label(label) if label.present?
    status = nil if status && !label_matches?(status['category'], current)
    status ||= default_status(current)
    status && status['origin_id']
  end

  def label_matches?(label_category, current)
    label_category == current || (current == 'open' && label_category == 'new' && !ZendeskCompat::TicketModel.native?)
  end

  def default_status(status_category)
    defaults = ZendeskCompat::Config.custom_statuses.select { |_id, status| status['category'] == status_category && status['default'] }
    origin_id = defaults.keys.first&.to_i
    statuses.find { |status| status['origin_id'] == origin_id } || statuses.find { |status| status['category'] == status_category }
  end

  def status_for_origin_id(origin_id)
    statuses.find { |status| status['origin_id'].to_s == origin_id.to_s }
  end

  # Atributos a gravar para um status do Zendesk (status e/ou custom_status_id). nil = inválido.
  # { native: valor do status do modelo, label: rótulo zd_status (ou nil), system_label:, category: }
  def attributes_for(status: nil, custom_status_id: nil)
    entry = custom_status_id.present? ? status_for_origin_id(custom_status_id) : nil
    return if custom_status_id.present? && entry.nil?

    zd_category = status.to_s.downcase.presence
    return if zd_category && ORDER.exclude?(zd_category)

    category = entry ? entry['category'] : zd_category
    return if category.nil?

    entry ||= default_status(category == 'closed' ? 'solved' : category)
    build_attributes(entry, category, zd_category)
  end

  def build_attributes(entry, category, zd_category)
    if ZendeskCompat::TicketModel.native?
      return { native: ZendeskCompat::TicketModel::NATIVE_STATUS[category], label: entry&.dig('label'), system_label: nil, category: category }
    end
    return if entry.nil?

    native = Servicedesk::TicketStatuses.native_status_for(entry['label'])
    system = zd_category == 'closed' ? SYSTEM_LABELS['closed'] : nil
    { native: native, label: entry['label'], system_label: system, category: entry['category'] }
  end

  # Expressão SQL da categoria (para a busca): mesma regra de category/1.
  def category_sql
    return native_category_sql if ZendeskCompat::TicketModel.native?

    whens = statuses.map do |status|
      native = Conversation.statuses[native_for_category(status['category'])]
      "WHEN conversations.custom_attributes->>'#{LABEL_ATTRIBUTE}' = #{quote(status['label'])} AND conversations.status = #{native} " \
        "THEN #{quote(status['category'])}"
    end
    natives = NATIVE_CATEGORY.map { |native, cat| "WHEN conversations.status = #{Conversation.statuses[native]} THEN #{quote(cat)}" }
    closed = "WHEN conversations.custom_attributes->>'#{SYSTEM_ATTRIBUTE}' = #{quote(SYSTEM_LABELS['closed'])} " \
             "AND conversations.status = #{Conversation.statuses['resolved']} THEN 'closed'"
    "(CASE #{closed} #{whens.join(' ')} #{natives.join(' ')} ELSE 'open' END)"
  end

  def native_category_sql
    whens = ENUM_CATEGORY.filter_map do |enum, cat|
      value = Conversation.statuses[enum]
      "WHEN conversations.status = #{value} THEN #{quote(cat)}" if value
    end
    "(CASE #{whens.join(' ')} ELSE 'open' END)"
  end

  def labels?
    ZendeskCompat::TicketModel.labels?
  end

  def statuses
    labels? ? Servicedesk::TicketStatuses.statuses : []
  end

  def find_label(label)
    labels? ? Servicedesk::TicketStatuses.find(label) : nil
  end

  def label_category(label)
    labels? ? Servicedesk::TicketStatuses.category_for(label) : nil
  end

  def quote(value)
    ActiveRecord::Base.connection.quote(value)
  end
end
# rubocop:enable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity, Metrics/ModuleLength
