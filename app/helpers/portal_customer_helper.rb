# ServiceDesk B2B: formatação das telas de solicitações do portal do cliente.
module PortalCustomerHelper
  SD_TIME_ZONE = 'America/Sao_Paulo'.freeze

  def sd_time(time, with_time: true)
    return '' if time.blank?

    local = time.in_time_zone(ENV.fetch('SD_PORTAL_TIME_ZONE', SD_TIME_ZONE))
    local.strftime(with_time ? '%d/%m/%Y %H:%M' : '%d/%m/%Y')
  end

  def sd_request_subject(conversation)
    subject = conversation.subject.presence || conversation.additional_attributes&.dig('mail_subject').presence ||
              conversation.custom_attributes&.dig('zd_assunto').presence
    return subject.to_s.truncate(140) if subject

    first = conversation.messages.where(private: false).where.not(content: [nil, '']).reorder(:created_at).first
    first ? first.content.to_s.squish.truncate(80) : "##{conversation.display_id}"
  end

  def sd_status_badge(conversation)
    status = PortalCustomers::RequestStatus.new(conversation)
    tag.span(status.label, class: "status-label status-label-request status-label-#{status.group}", data: { status: status.group },
                           title: status.label)
  end

  def sd_message_from_customer?(message)
    message.incoming? && message.sender_type == 'Contact'
  end

  def sd_message_author(message)
    sender = message.sender
    case message.sender_type
    when 'User'
      sender.try(:available_name).presence || sender.try(:name).presence || I18n.t('public_portal.sd.requests.support_team')
    when 'Contact'
      sender.try(:name).presence || sender.try(:email).presence || I18n.t('public_portal.sd.requests.you')
    else
      I18n.t('public_portal.sd.requests.support_team')
    end
  end

  def sd_initial(name)
    name.to_s.strip.first.to_s.upcase.presence || '?'
  end

  # Conteúdo público da mensagem em HTML seguro (Markdown do agente ou texto do cliente).
  def sd_message_html(message)
    html = ChatwootMarkdownRenderer.new(message.content.to_s).render_message(hardbreaks: true)
    sanitize(html, tags: %w[p br strong em b i u s del a ul ol li blockquote code pre h1 h2 h3 h4 table thead tbody tr th td hr span],
                   attributes: %w[href title target rel])
  end

  def sd_assignee_name(conversation)
    assignee = conversation.assignee
    return '—' if assignee.blank?

    assignee.try(:available_name).presence || assignee.name
  end

  # ---- Central de Ajuda (tema Copenhagen): só artigos publicados que o visitante pode ver
  def sd_visible_articles(relation)
    relation.published.visible_to_segments(portal_visible_segment_ids)
  end

  # Categorias do Zendesk (topo) que têm artigo visível nelas ou nas seções (subcategorias)
  def sd_home_categories(portal, locale)
    categories = portal.categories.where(locale: locale)
    with_articles = sd_visible_articles(portal.articles.where(locale: locale)).where.not(category_id: nil).distinct.pluck(:category_id)
    top_ids = categories.where(id: with_articles).pluck(:parent_category_id, :id).map { |parent_id, id| parent_id || id }
    categories.where(id: top_ids, parent_category_id: nil).order(:position, :id)
  end

  # Seções (subcategorias) com artigo visível
  def sd_sections(category)
    category.sub_categories.order(:position, :id).select { |section| sd_visible_articles(section.articles).exists? }
  end

  def sd_category_articles(category)
    sd_visible_articles(category.articles).order(:position, :id)
  end

  def sd_recent_articles(portal, locale, limit: 5)
    sd_visible_articles(portal.articles.where(locale: locale)).includes(:category).reorder(updated_at: :desc).limit(limit)
  end

  def sd_article_link(article)
    public_portal_article_path(article.portal.slug, article.slug)
  end

  def sd_category_link(category)
    public_portal_category_path(category.portal.slug, category.locale, category.slug)
  end

  def sd_category_trail(category)
    return [] if category.blank?

    trail = [[category.name, sd_category_link(category)]]
    trail.unshift([category.parent_category.name, sd_category_link(category.parent_category)]) if category.parent_category
    trail
  end
end
