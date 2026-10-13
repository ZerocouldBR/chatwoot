# Execução das ações do ServiceDesk em ActionService (base de Macros::ExecutionService e
# AutomationRules::ActionService). Parâmetros e validação: Servicedesk::ConversationActionParams.
# Um valor que deixou de ser válido depois de salvo (ex.: opção removida da lista) é ignorado com log,
# como as ações nativas fazem com time ou agente inexistente.
module Servicedesk::ConversationActions
  # Os nomes seguem o nome da ação gravada (ActionService chama send(action_name)).
  # rubocop:disable Naming/AccessorMethodName
  def set_custom_attribute(params)
    key, value = Array(params)
    result = servicedesk_action_params.custom_attribute(key, value)
    return log_skipped_servicedesk_action('set_custom_attribute', result.error) unless result.ok?

    @conversation.with_lock do
      attributes = (@conversation.custom_attributes || {}).dup
      result.value.nil? ? attributes.delete(key.to_s) : attributes[key.to_s] = result.value
      @conversation.update!(custom_attributes: attributes)
    end
  end

  def set_ticket_status(params)
    result = servicedesk_action_params.ticket_status(Array(params).first)
    return log_skipped_servicedesk_action('set_ticket_status', result.error) unless result.ok?

    label = result.value['label']
    native = Servicedesk::TicketStatuses.native_status_for(label)
    @conversation.with_lock do
      attributes = (@conversation.custom_attributes || {}).merge(Servicedesk::TicketStatuses.attribute_key => label)
      @conversation.update!(custom_attributes: attributes, status: native)
    end
  end
  # rubocop:enable Naming/AccessorMethodName

  def change_subject(params)
    result = servicedesk_action_params.subject(Array(params).first)
    return log_skipped_servicedesk_action('change_subject', result.error) unless result.ok?

    @conversation.with_lock do
      attributes = (@conversation.additional_attributes || {}).merge('mail_subject' => result.value)
      @conversation.update!(additional_attributes: attributes)
    end
  end

  private

  def servicedesk_action_params
    @servicedesk_action_params ||= Servicedesk::ConversationActionParams.new(@conversation.account)
  end

  def log_skipped_servicedesk_action(action_name, reason)
    Rails.logger.info({ event: 'servicedesk_action_skipped', action: action_name, reason: reason,
                        account_id: @conversation.account_id, conversation_id: @conversation.id }.to_json)
    nil
  end
end
