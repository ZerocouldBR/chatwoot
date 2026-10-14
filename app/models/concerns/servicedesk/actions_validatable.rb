# Valida os parâmetros das ações do ServiceDesk (set_custom_attribute, set_ticket_status, change_subject)
# em Macro. O nome da ação continua sendo validado pela lista do modelo.
module Servicedesk::ActionsValidatable
  extend ActiveSupport::Concern

  included do
    validate :validate_servicedesk_action_params
  end

  private

  def validate_servicedesk_action_params
    return if actions.blank? || account.blank?

    Servicedesk::ConversationActionParams.new(account).errors_for(actions).each do |message|
      errors.add(:actions, message)
    end
  end
end
