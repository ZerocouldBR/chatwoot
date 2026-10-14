# /api/v2/tickets (show, show_many, create, update). O nó "Zendesk" do n8n usa GET e PUT /tickets/:id.json.
class ZendeskCompat::V2::TicketsController < ZendeskCompat::BaseController
  def show
    conversation = find_ticket!(params[:id])
    render json: with_sideloads({ ticket: presenter.present(conversation) }, [conversation])
  end

  def show_many
    ids = params[:ids].to_s.split(',').filter_map { |id| ZendeskCompat::Ids.integer(id) }.first(100)
    conversations = current_account.conversations.where(display_id: ids).order(:display_id).to_a
    render json: with_sideloads({ tickets: conversations.map { |c| presenter.present(c) }, next_page: nil, previous_page: nil,
                                  count: conversations.size }, conversations)
  end

  def create
    conversation = ZendeskCompat::TicketCreator.new(context, ticket_param).perform
    response.headers['Location'] = context.api_url("tickets/#{conversation.display_id}.json")
    audit = ZendeskCompat::AuditsBuilder.new(context, conversation).audits.first
    render json: { ticket: presenter.present(conversation), audit: audit }, status: :created
  end

  def update
    conversation = find_ticket!(params[:id])
    last_change_id = Servicedesk::TicketAudit.where(conversation_id: conversation.id).maximum(:id)
    updater = ZendeskCompat::TicketUpdater.new(context, conversation, ticket_param)
    conversation = updater.perform
    audit = ZendeskCompat::AuditsBuilder.new(context, conversation).request_audit(after_change_id: last_change_id, message: updater.message)
    render json: { ticket: presenter.present(conversation), audit: audit }
  end

  private

  def ticket_param
    ticket = body_params['ticket']
    raise ZendeskCompat::Error, 'Parâmetro "ticket" ausente ou inválido' unless ticket.is_a?(Hash)

    ticket
  end

  def presenter
    @presenter ||= ZendeskCompat::TicketPresenter.new(context)
  end

  # include=users (solicitante, responsável, CCs e seguidores), como o sideload do Zendesk.
  def with_sideloads(payload, _conversations)
    return payload unless params[:include].to_s.split(',').include?('users')

    tickets = payload[:ticket] ? [payload[:ticket]] : payload[:tickets]
    ids = tickets.flat_map { |t| [t[:requester_id], t[:submitter_id], t[:assignee_id], *t[:collaborator_ids]] }.compact.uniq
    user_presenter = ZendeskCompat::UserPresenter.new(context)
    payload.merge(users: context.directory.actors(ids).map { |record| user_presenter.present(record) })
  end
end
