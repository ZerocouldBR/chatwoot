class Macros::ExecutionService < ActionService
  # ServiceDesk M5.1 (macro_fill_editor): estas ações vão para o editor do agente, que revisa e envia.
  # O backend nunca as executa nesse modo, nem em execução em massa: nada sai para o cliente sem revisão.
  EDITOR_ACTIONS = %w[send_message send_attachment].freeze

  def initialize(macro, conversation, user)
    super(conversation)
    @macro = macro
    @account = macro.account
    @user = user
    Current.user = user
  end

  def perform
    @macro.actions.each do |action|
      action = action.with_indifferent_access
      next if filled_in_editor?(action[:action_name])

      begin
        send(action[:action_name], action[:action_params])
      rescue StandardError => e
        ChatwootExceptionTracker.new(e, account: @account).capture_exception
      end
    end
  ensure
    Current.reset
  end

  private

  def fill_editor?
    @fill_editor = @account.macro_fill_editor? if @fill_editor.nil?
    @fill_editor
  end

  # A nota privada vai para o editor só quando a macro não tem resposta pública (o editor tem um modo por vez);
  # com resposta pública, a nota é interna e continua sendo gravada direto.
  def filled_in_editor?(action_name)
    return false unless fill_editor?
    return true if EDITOR_ACTIONS.include?(action_name)

    action_name == 'add_private_note' && @macro.actions.none? { |action| action.with_indifferent_access[:action_name] == 'send_message' }
  end

  def assign_agent(agent_ids)
    agent_ids = agent_ids.map { |id| id == 'self' ? @user.id : id }
    super(agent_ids)
  end

  def add_private_note(message)
    return if conversation_a_tweet?

    params = { content: message[0], private: true }

    # Added reload here to ensure conversation us persistent with the latest updates
    mb = Messages::MessageBuilder.new(@user, @conversation.reload, params)
    mb.perform
  end

  def send_message(message)
    return if conversation_a_tweet?

    params = { content: message[0], private: false }

    # Added reload here to ensure conversation us persistent with the latest updates
    mb = Messages::MessageBuilder.new(@user, @conversation.reload, params)
    mb.perform
  end

  def send_attachment(blob_ids)
    return if conversation_a_tweet?

    return unless @macro.files.attached?

    blobs = ActiveStorage::Blob.where(id: blob_ids)

    return if blobs.blank?

    params = { content: nil, private: false, attachments: blobs }

    # Added reload here to ensure conversation us persistent with the latest updates
    mb = Messages::MessageBuilder.new(@user, @conversation.reload, params)
    mb.perform
  end

  def send_webhook_event(webhook_url)
    payload = @conversation.webhook_data.merge(event: 'macro.executed')
    WebhookJob.perform_later(webhook_url.first, payload)
  end
end

Macros::ExecutionService.include_mod_with('Macros::ExecutionService')
