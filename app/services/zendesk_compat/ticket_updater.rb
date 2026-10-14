# PUT /api/v2/tickets/:id (e o nó Zendesk "ticket: update" do n8n): aplica o objeto "ticket" do Zendesk na conversa.
# Suportado: status, custom_status_id, assignee_id/assignee_email, group_id, priority, type, subject, tags,
# additional_tags, remove_tags, custom_fields/fields, email_ccs, collaborator_ids, external_id, due_at, comment
# (body/html_body, public, author_id, uploads) e safe_update/updated_stamp. Tudo numa transação; o comentário entra
# depois das mudanças, como no Zendesk. Erros de validação -> ZendeskCompat::Error::RecordInvalid (422 no formato do Zendesk).
# Status, assunto, tipo, vencimento e CCs são gravados pelo modelo de ticket do fork (ZendeskCompat::TicketModel).
class ZendeskCompat::TicketUpdater
  attr_reader :conversation, :message

  def initialize(context, conversation, ticket_params)
    @context = context
    @conversation = conversation
    @params = (ticket_params || {}).to_h.with_indifferent_access
    @errors = {}
  end

  def perform
    check_conflict!
    Servicedesk::TicketAuditContext.with('api') do
      ActiveRecord::Base.transaction do
        assign_attributes
        raise_errors!
        @conversation.save! if @conversation.changed? || @labels_changed
        ZendeskCompat::TicketModel.write_cc_emails(@conversation, @cc_list) if @cc_list && ZendeskCompat::TicketModel.native?
        @message = ZendeskCompat::CommentCreator.new(@context, @conversation, @params[:comment]).perform if @params[:comment].present?
      end
    end
    @conversation.reload
  end

  private

  def check_conflict!
    return unless ActiveModel::Type::Boolean.new.cast(@params[:safe_update])
    return if @params[:updated_stamp].blank?

    stamp = Time.zone.parse(@params[:updated_stamp].to_s)
    return if stamp && @conversation.updated_at.to_i <= stamp.to_i

    raise ZendeskCompat::Error::UpdateConflict
  end

  def assign_attributes
    assign_status
    assign_assignee
    assign_group
    assign_priority
    assign_custom_attributes
    assign_ticket_fields
    assign_ccs
    assign_tags
  end

  def assign_status
    return unless @params.key?(:status) || @params.key?(:custom_status_id)

    result = ZendeskCompat::StatusTranslator.attributes_for(status: @params[:status], custom_status_id: @params[:custom_status_id])
    return add_error(:status, "Status: #{@params[:status] || @params[:custom_status_id]} não é um status válido") if result.nil?

    @conversation.status = result[:native]
    @custom_attributes = custom_attributes.merge(ZendeskCompat::StatusTranslator::LABEL_ATTRIBUTE => result[:label]) if result[:label]
    @custom_attributes[ZendeskCompat::StatusTranslator::SYSTEM_ATTRIBUTE] = result[:system_label] if result[:system_label]
  end

  def assign_assignee
    if @params.key?(:assignee_email) && !@params.key?(:assignee_id)
      agent = @context.directory.agent_by_email(@params[:assignee_email])
      return add_error(:assignee, "Assignee: #{@params[:assignee_email]} não é um agente") if agent.nil?

      return assign_to(agent)
    end
    return unless @params.key?(:assignee_id)

    assign_by_zendesk_id(@params[:assignee_id])
  end

  def assign_by_zendesk_id(id)
    return assign_to(nil) if id.blank?

    agent = @context.directory.agent(id)
    return assign_to(agent) if agent

    bot = @context.directory.actor(id)
    return assign_to(bot) if bot.is_a?(AgentBot) && @conversation.respond_to?(:ai_assignee=)

    add_error(:assignee, "Assignee: #{id} não é um agente da conta")
  end

  def assign_to(record)
    @conversation.assignee = record.is_a?(User) ? record : nil
    return unless @conversation.respond_to?(:ai_assignee=)

    @conversation.ai_assignee = record if record.is_a?(AgentBot)
    @conversation.ai_assignee = nil if record.nil? && @conversation.ai_assignee.is_a?(AgentBot)
  end

  def assign_group
    return unless @params.key?(:group_id)
    return @conversation.team = nil if @params[:group_id].blank?

    team = @context.directory.team(@params[:group_id])
    team ? @conversation.team = team : add_error(:group, "Group: #{@params[:group_id]} não existe")
  end

  def assign_priority
    return unless @params.key?(:priority)

    value = @params[:priority].presence
    native = value && ZendeskCompat::Config.priorities[value.to_s]
    return add_error(:priority, "Priority: #{value} não é uma prioridade válida") if value && native.nil?

    @conversation.priority = native
  end

  def assign_custom_attributes
    attrs = custom_attributes.dup
    attrs.merge!(@context.fields.attributes_from(@params[:custom_fields])) if @params.key?(:custom_fields)
    attrs.merge!(@context.fields.attributes_from(@params[:fields])) if @params.key?(:fields)
    attrs['zd_id_externo'] = @params[:external_id] if @params.key?(:external_id)
    attrs.compact!
    @conversation.custom_attributes = attrs if attrs != (@conversation.custom_attributes || {})
  end

  def assign_ccs
    changes = Array(@params[:email_ccs])
    changes += Array(@params[:collaborator_ids]).map { |id| { user_id: id, action: 'put' } }
    changes += Array(@params[:collaborators]).map { |email| { user_email: email.is_a?(Hash) ? email['email'] : email, action: 'put' } }
    return if changes.empty?

    @cc_list = ZendeskCompat::CcList.apply(ZendeskCompat::TicketModel.cc_emails(@conversation), changes, @context.directory)
    ZendeskCompat::TicketModel.write_cc_emails(@conversation, @cc_list) unless ZendeskCompat::TicketModel.native?
  end

  # assunto, tipo e vencimento: colunas no modelo nativo, atributos zd_* no legado
  def assign_ticket_fields
    model = ZendeskCompat::TicketModel
    model.assign_subject(@conversation, @params[:subject]) if @params.key?(:subject)
    invalid_type = @params.key?(:type) && model.assign_type(@conversation, @params[:type]) == :invalid
    add_error(:type, "Type: #{@params[:type]} não é um tipo válido") if invalid_type
    model.assign_due_at(@conversation, @params[:due_at]) if @params.key?(:due_at)
  rescue ArgumentError
    add_error(:due_at, "Due at: #{@params[:due_at]} não é uma data válida")
  end

  def assign_tags
    current = @conversation.label_list.to_a
    labels = @params.key?(:tags) ? ZendeskCompat::Tags.normalize(@params[:tags]) : current.dup
    labels |= ZendeskCompat::Tags.normalize(@params[:additional_tags]) if @params.key?(:additional_tags)
    labels -= ZendeskCompat::Tags.normalize(@params[:remove_tags]) if @params.key?(:remove_tags)
    return if labels.sort == current.sort

    @conversation.label_list = labels
    @labels_changed = true
  end

  def custom_attributes
    @custom_attributes ||= (@conversation.custom_attributes || {}).dup
  end

  def add_error(field, description)
    (@errors[field] ||= []) << { description: description, error: 'InvalidValue' }
  end

  def raise_errors!
    raise ZendeskCompat::Error::RecordInvalid, @errors if @errors.any?
  end
end
