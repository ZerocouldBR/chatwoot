# ServiceDesk B2B: "Enviar uma solicitação" pelo portal. Cria a conversa (ticket) na inbox do formulário,
# com o contato logado como solicitante, a descrição como primeira mensagem e os anexos.
# O ticket nasce Novo (status nativo new_ticket), com o assunto na coluna nativa `subject` e a empresa do
# solicitante (company_id, preenchida pelo modelo). A auditoria (conversation_events) registra o contato como
# autor (via "customer"). Os atributos seguem o mapa do Zendesk (docs/CAMPOS.md): zd_assunto, zd_formulario,
# zd_canal = Central de Ajuda, zd_status = Novo e os campos extras do formulário.
class PortalCustomers::CreateRequestService
  MAX_ATTACHMENTS = 10
  MAX_SUBJECT = 255
  MAX_DESCRIPTION = 20_000

  class Error < StandardError
    attr_reader :messages

    def initialize(messages)
      @messages = Array(messages)
      super(@messages.join(', '))
    end
  end

  pattr_initialize [:portal!, :contact!, :form_id, :subject, :description, { fields: {}, attachments: [] }]

  def perform
    forms = PortalCustomers::RequestForms.new(portal: portal)
    form = forms.find(form_id)
    inbox = forms.inbox_for(form)
    raise Error, I18n.t('public_portal.sd.requests.errors.inbox_not_configured') if inbox.blank?

    custom_attributes, field_errors = forms.extract_fields(form, fields)
    validate!(field_errors)

    as_contact do
      ActiveRecord::Base.transaction do
        conversation = create_conversation(inbox, form, custom_attributes)
        create_message(conversation)
        conversation
      end
    end
  end

  private

  # Autor da auditoria (conversation_events, via "customer"): o contato do portal, só durante a operação.
  def as_contact
    previous = Current.contact
    Current.contact = contact
    yield
  ensure
    Current.contact = previous
  end

  def validate!(field_errors)
    errors = field_errors.map { |label| I18n.t('public_portal.sd.requests.errors.field_invalid', field: label) }
    errors << I18n.t('public_portal.sd.requests.errors.subject_required') if clean_subject.blank?
    errors << I18n.t('public_portal.sd.requests.errors.description_required') if description.to_s.strip.blank?
    errors << I18n.t('public_portal.sd.requests.errors.too_many_attachments', count: MAX_ATTACHMENTS) if uploads.size > MAX_ATTACHMENTS
    raise Error, errors if errors.any?
  end

  def clean_subject
    subject.to_s.squish.first(MAX_SUBJECT)
  end

  def uploads
    @uploads ||= Array(attachments).compact_blank.select { |file| file.respond_to?(:content_type) }
  end

  def create_conversation(inbox, form, custom_attributes)
    contact_inbox = ContactInboxBuilder.new(contact: contact, inbox: inbox).perform
    Conversation.create!(
      account_id: portal.account_id, inbox_id: inbox.id, contact_id: contact.id, contact_inbox_id: contact_inbox.id,
      subject: clean_subject.truncate(150),
      additional_attributes: { 'mail_subject' => clean_subject, 'source' => 'help_center', 'portal_slug' => portal.slug },
      custom_attributes: custom_attributes.merge(
        'zd_assunto' => clean_subject, 'zd_formulario' => form.name, 'zd_canal' => 'Central de Ajuda',
        'zd_status' => 'Novo', 'zd_status_sistema' => 'Novo'
      )
    )
  end

  def create_message(conversation)
    message = conversation.messages.new(
      account_id: conversation.account_id, inbox_id: conversation.inbox_id, sender: contact,
      message_type: :incoming, content: description.to_s.strip.first(MAX_DESCRIPTION)
    )
    PortalCustomers::AttachmentBuilder.new(message: message, uploads: uploads).build
    message.save!
  rescue ActiveRecord::RecordInvalid => e
    raise Error, PortalCustomers::AttachmentBuilder.error_messages(e.record)
  end
end
