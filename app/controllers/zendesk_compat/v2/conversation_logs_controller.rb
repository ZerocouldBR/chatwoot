# GET /api/v2/tickets/:ticket_id/conversation_log: eventos da conversa (mensageria) no formato do Zendesk.
class ZendeskCompat::V2::ConversationLogsController < ZendeskCompat::BaseController
  def show
    events = ZendeskCompat::ConversationLogBuilder.new(context, find_ticket!).events
    events = events.reverse if params[:sort_order].to_s.casecmp('desc').zero?
    render json: { events: events, links: { next: nil, prev: nil }, meta: { has_more: false, after_cursor: nil, before_cursor: nil } }
  end
end
