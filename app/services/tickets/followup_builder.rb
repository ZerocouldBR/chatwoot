# Builds the follow-up ticket for a reply to a closed ticket (Zendesk "follow-up tickets").
# The follow-up keeps requester, inbox, subject, company and tags, and starts fresh on
# status, priority, type, group and assignee. Comments are not copied; it links back instead.
class Tickets::FollowupBuilder
  pattr_initialize [:source!, :additional_attributes]

  def build
    source.account.conversations.new(
      inbox: source.inbox,
      contact: source.contact,
      contact_inbox: source.contact_inbox,
      followup_source: source,
      subject: source.subject,
      company_id: source.company_id,
      label_list: source.label_list,
      additional_attributes: additional_attributes || {}
    )
  end
end
