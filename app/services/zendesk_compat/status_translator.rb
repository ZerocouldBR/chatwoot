# Status do Zendesk <-> status do ServiceDesk (decisão 1: rótulo em zd_status, status nativo pela categoria).
#   leitura: categoria do rótulo zd_status (new/open/pending/hold/solved) e "closed" quando zd_status_sistema = Fechado;
#            sem rótulo, pelo status nativo (open -> open, pending -> new, snoozed -> pending, resolved -> solved)
#   escrita: status do Zendesk -> rótulo padrão da categoria (custom_statuses[].default); custom_status_id -> rótulo
# rubocop:disable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
module ZendeskCompat::StatusTranslator
  ORDER = %w[new open pending hold solved closed].freeze
  NATIVE_CATEGORY = { 'open' => 'open', 'pending' => 'new', 'snoozed' => 'pending', 'resolved' => 'solved' }.freeze
  SYSTEM_LABELS = { 'closed' => 'Fechado', 'deleted' => 'Excluído' }.freeze
  SYSTEM_ATTRIBUTE = 'zd_status_sistema'.freeze

  module_function

  def category(conversation)
    attributes = conversation.custom_attributes || {}
    system_label = attributes[SYSTEM_ATTRIBUTE]
    return 'closed' if system_label == SYSTEM_LABELS['closed'] && conversation.resolved?
    return 'deleted' if system_label == SYSTEM_LABELS['deleted']

    label = attributes[Servicedesk::TicketStatuses.attribute_key]
    status_category = Servicedesk::TicketStatuses.category_for(label) if label.present?
    status_category = NATIVE_CATEGORY[conversation.status] if status_category.nil? || !consistent?(status_category, conversation)
    status_category || 'open'
  end

  # O rótulo pode ter ficado para trás se alguém mudou só o status nativo pelo painel padrão do Chatwoot.
  def consistent?(status_category, conversation)
    native = native_for_category(status_category)
    native.nil? || native == conversation.status || (conversation.pending? && status_category == 'new')
  end

  def native_for_category(status_category)
    status = Servicedesk::TicketStatuses.statuses.find { |entry| entry['category'] == status_category }
    status && Servicedesk::TicketStatuses.native_status_for(status['label'])
  end

  def custom_status_id(conversation)
    label = (conversation.custom_attributes || {})[Servicedesk::TicketStatuses.attribute_key]
    status = Servicedesk::TicketStatuses.find(label) if label.present?
    status = nil if status && !consistent?(status['category'], conversation)
    status ||= default_status(category(conversation) == 'closed' ? 'solved' : category(conversation))
    status && status['origin_id']
  end

  def default_status(status_category)
    defaults = ZendeskCompat::Config.custom_statuses.select { |_id, status| status['category'] == status_category && status['default'] }
    origin_id = defaults.keys.first&.to_i
    statuses = Servicedesk::TicketStatuses.statuses
    statuses.find { |status| status['origin_id'] == origin_id } || statuses.find { |status| status['category'] == status_category }
  end

  def status_for_origin_id(origin_id)
    Servicedesk::TicketStatuses.statuses.find { |status| status['origin_id'].to_s == origin_id.to_s }
  end

  # Atributos a gravar para um status do Zendesk (status e/ou custom_status_id). nil = inválido.
  def attributes_for(status: nil, custom_status_id: nil)
    entry = custom_status_id.present? ? status_for_origin_id(custom_status_id) : nil
    return if custom_status_id.present? && entry.nil?

    zd_category = status.to_s.downcase.presence
    return if zd_category && ORDER.exclude?(zd_category)

    entry ||= default_status(zd_category == 'closed' ? 'solved' : zd_category)
    return if entry.nil?

    build_attributes(entry, zd_category)
  end

  def build_attributes(entry, zd_category)
    native = Servicedesk::TicketStatuses.native_status_for(entry['label'])
    system = zd_category == 'closed' ? SYSTEM_LABELS['closed'] : nil
    { native: native, label: entry['label'], system_label: system, category: entry['category'] }
  end

  # Expressão SQL da categoria (para a busca): mesma regra de category/1.
  def category_sql
    key = Servicedesk::TicketStatuses.attribute_key
    whens = Servicedesk::TicketStatuses.statuses.map do |status|
      native = Conversation.statuses[native_for_category(status['category'])]
      "WHEN conversations.custom_attributes->>'#{key}' = #{quote(status['label'])} AND conversations.status = #{native} " \
        "THEN #{quote(status['category'])}"
    end
    natives = NATIVE_CATEGORY.map { |native, cat| "WHEN conversations.status = #{Conversation.statuses[native]} THEN #{quote(cat)}" }
    closed = "WHEN conversations.custom_attributes->>'#{SYSTEM_ATTRIBUTE}' = #{quote(SYSTEM_LABELS['closed'])} " \
             "AND conversations.status = #{Conversation.statuses['resolved']} THEN 'closed'"
    "(CASE #{closed} #{whens.join(' ')} #{natives.join(' ')} ELSE 'open' END)"
  end

  def quote(value)
    ActiveRecord::Base.connection.quote(value)
  end
end
# rubocop:enable Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
