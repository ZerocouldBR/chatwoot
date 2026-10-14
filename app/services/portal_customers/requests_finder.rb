# ServiceDesk B2B: o que o contato logado pode ver em "Minhas solicitações" e "Solicitações da organização".
#
# - Minhas: conversas em que ele é o solicitante (contact_id), de qualquer canal, como no Zendesk.
# - Organização: conversas de contatos da mesma empresa (company_id), só quando o portal liga
#   customer_portal.organization_requests E a empresa compartilha (companies.custom_attributes
#   portal_shared_requests = true; equivale a organization.shared_tickets do Zendesk). Responder em
#   ticket de outro membro exige também portal_shared_comments = true (shared_comments do Zendesk).
#   Na B2B as 7.416 organizações têm shared_tickets = false, então a aba fica oculta.
class PortalCustomers::RequestsFinder
  PER_PAGE = 20

  pattr_initialize [:portal!, :contact!]

  def mine
    base.where(contact_id: contact.id)
  end

  def organization
    return base.none unless organization_enabled?

    base.where(contact_id: portal.account.contacts.where(company_id: contact.company_id).select(:id))
  end

  def organization_enabled?
    return false unless portal.organization_requests_enabled? && contact.company_id.present?

    company_flag('portal_shared_requests')
  end

  def find(display_id)
    conversation = base.find_by(display_id: display_id)
    return if conversation.blank?
    return conversation if conversation.contact_id == contact.id
    return conversation if organization_enabled? && conversation.contact&.company_id == contact.company_id

    nil
  end

  # Em ticket fechado a resposta abre um acompanhamento (PortalCustomers::ReplyService), com a mesma permissão.
  def can_reply?(conversation)
    return true if conversation.contact_id == contact.id

    organization_enabled? && company_flag('portal_shared_comments')
  end

  def search(relation, query:, status:, page:)
    relation = PortalCustomers::RequestStatus.filter(relation, status) if PortalCustomers::RequestStatus::GROUPS.include?(status)
    if query.present?
      term = "%#{ActiveRecord::Base.sanitize_sql_like(query.to_s.strip.first(100))}%"
      relation = relation.where(
        "conversations.subject ILIKE :term OR conversations.additional_attributes->>'mail_subject' ILIKE :term " \
        "OR conversations.custom_attributes->>'zd_assunto' ILIKE :term " \
        'OR CAST(conversations.display_id AS TEXT) = :exact', term: term, exact: query.to_s.strip.delete('#')
      )
    end
    relation.order(last_activity_at: :desc, id: :desc).page(page).per(PER_PAGE)
  end

  private

  def base
    portal.account.conversations.includes(:contact, :assignee)
  end

  def company_flag(key)
    @company ||= Company.find_by(id: contact.company_id, account_id: portal.account_id)
    ActiveModel::Type::Boolean.new.cast((@company&.custom_attributes || {})[key]) == true
  end
end
