# POST /api/v2/tickets: cria a conversa a partir do objeto "ticket" do Zendesk.
#   caixa: recipient (endereço da caixa de e-mail) -> ZENDESK_COMPAT_DEFAULT_INBOX_ID -> 1ª caixa de e-mail -> 1ª caixa API
#   solicitante: requester_id ou requester {email, name, phone} (contato criado se não existir)
#   o restante (status, responsável, grupo, etiquetas, campos, CCs, comentário) segue o ZendeskCompat::TicketUpdater
class ZendeskCompat::TicketCreator
  def initialize(context, ticket_params)
    @context = context
    @params = (ticket_params || {}).to_h.with_indifferent_access
  end

  def perform
    inbox = resolve_inbox
    contact = resolve_contact
    conversation = nil
    ActiveRecord::Base.transaction do
      contact_inbox = ContactInboxBuilder.new(contact: contact, inbox: inbox, source_id: nil).perform
      conversation = Conversation.create!(account: @context.account, inbox: inbox, contact: contact, contact_inbox: contact_inbox,
                                          additional_attributes: initial_additional_attributes)
      ZendeskCompat::TicketUpdater.new(@context, conversation, update_params).perform
    end
    conversation.reload
  end

  private

  def update_params
    params = @params.except(:requester, :requester_id, :recipient, :via, :brand_id, :ticket_form_id)
    unless params.key?(:custom_status_id) # como o Zendesk: "new" sem responsável, "open" com responsável
      assigned = params[:assignee_id].present? || params[:assignee_email].present?
      params[:status] ||= assigned ? 'open' : 'new'
    end
    params
  end

  def initial_additional_attributes
    subject = @params[:subject].presence || @params.dig(:comment, :body).to_s.truncate(80).presence
    subject ? { 'mail_subject' => subject } : {}
  end

  def resolve_inbox
    inboxes = @context.account.inboxes
    by_recipient = inboxes.joins("INNER JOIN channel_email ON channel_email.id = inboxes.channel_id AND inboxes.channel_type = 'Channel::Email'")
                          .find_by('LOWER(channel_email.email) = ?', @params[:recipient].to_s.downcase)
    by_recipient || default_inbox || invalid!(:recipient, 'Nenhuma caixa de entrada para criar o ticket')
  end

  def default_inbox
    inboxes = @context.account.inboxes
    configured = ENV.fetch('ZENDESK_COMPAT_DEFAULT_INBOX_ID', nil)
    (configured && inboxes.find_by(id: configured)) || inboxes.find_by(channel_type: 'Channel::Email') ||
      inboxes.find_by(channel_type: 'Channel::Api')
  end

  def resolve_contact
    return requester_by_id if @params[:requester_id].present?

    requester = @params[:requester].is_a?(Hash) ? @params[:requester].with_indifferent_access : {}
    email = requester[:email].to_s.strip.downcase
    invalid!(:requester, 'Requester: informe requester_id ou requester.email') if email.blank?

    @context.directory.contact_by_email(email) ||
      @context.account.contacts.create!(email: email, name: requester[:name].presence || email.split('@').first,
                                        phone_number: requester[:phone].presence)
  end

  def requester_by_id
    record = @context.directory.actor(@params[:requester_id])
    record = @context.directory.contact_by_email(record.email) if record.is_a?(User)
    record.is_a?(Contact) ? record : invalid!(:requester, "Requester: #{@params[:requester_id]} não existe")
  end

  def invalid!(field, description)
    raise ZendeskCompat::Error::RecordInvalid, { field => [{ description: description, error: 'InvalidValue' }] }
  end
end
