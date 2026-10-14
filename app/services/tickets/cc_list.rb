# Reads and changes the CC list of a ticket (at most 48 people, like Zendesk).
# The requester and the inbox's own support addresses are never CCs.
class Tickets::CcList
  MAX_CCS = 48

  pattr_initialize :conversation

  def emails
    conversation.conversation_ccs.order(:id).pluck(:email)
  end

  # Adds the addresses that are not CCs yet; extra addresses beyond the limit are dropped.
  def add(addresses, author:, via:)
    current = emails
    new_emails = (normalize(addresses) - excluded_emails - current).reject { |email| inbound_reply_address?(email) }
                                                                   .first(MAX_CCS - current.size)
    return current if new_emails.empty?

    new_emails.each { |email| conversation.conversation_ccs.create!(account_id: conversation.account_id, email: email) }
    record_change(current, emails, author, via)
  end

  def remove(address, author:, via:)
    current = emails
    conversation.conversation_ccs.where(email: address.to_s.strip.downcase).destroy_all
    updated = emails
    record_change(current, updated, author, via) if updated != current
    updated
  end

  private

  def normalize(addresses)
    Array(addresses).flatten.compact.map { |address| address.to_s.strip.downcase }.grep(Devise.email_regexp).uniq
  end

  def excluded_emails
    channel = conversation.inbox.channel
    support = channel.is_a?(Channel::Email) ? [channel.email, channel.forward_to_email, channel.imap_login] : []
    [conversation.contact.email, *support].compact_blank.map(&:downcase)
  end

  # reply+<uuid>@<inbound domain> addresses route mail into the helpdesk; they are not people.
  def inbound_reply_address?(email)
    domain = conversation.account.inbound_email_domain
    domain.present? && email.end_with?("@#{domain.downcase}")
  end

  def record_change(previous, current, author, via)
    conversation.record_ticket_event(event_type: 'change', field_name: 'ccs', previous_value: previous, value: current, author: author, via: via)
    current
  end
end
