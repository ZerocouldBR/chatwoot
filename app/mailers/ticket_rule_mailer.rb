# E-mail sent to agents by a trigger or automation (Zendesk "Email user" / "Email group" for agents).
class TicketRuleMailer < ApplicationMailer
  def agent_notification(conversation, emails:, subject:, body:)
    return unless smtp_config_set_or_development?

    @conversation = conversation
    @body = body
    @action_url = app_account_conversation_url(account_id: conversation.account_id, id: conversation.display_id)
    mail(to: emails, subject: subject)
  end
end
