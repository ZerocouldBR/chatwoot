# Zendesk-style ticket placeholders: {{ticket.id}}, {{ticket.title}}, {{ticket.status}}, {{ticket.requester.name}}...
class TicketDrop < BaseDrop
  include Rails.application.routes.url_helpers

  def id
    @obj.display_id
  end

  def title
    @obj.subject
  end

  def status
    I18n.t("tickets.statuses.#{@obj.status}")
  end

  def priority
    @obj.priority && I18n.t("tickets.priorities.#{@obj.priority}")
  end

  def ticket_type
    @obj.ticket_type && I18n.t("tickets.types.#{@obj.ticket_type}")
  end

  def url
    app_account_conversation_url(account_id: @obj.account_id, id: @obj.display_id)
  end

  def requester
    ContactDrop.new(@obj.contact)
  end

  def assignee
    UserDrop.new(@obj.assignee) if @obj.assignee
  end

  def group
    @obj.team&.name
  end

  def description
    first_public_message&.content
  end

  def latest_comment
    @obj.messages.chat.where(private: false).last&.content
  end

  private

  def first_public_message
    @obj.messages.chat.where(private: false).first
  end
end
