# GET /api/v2/search(.json)?query=... e /search/count: tickets (type:ticket, padrão) e usuários (type:user).
# Resultados com result_type, ordenação sort_by=created_at|updated_at|status|priority e sort_order, máx. 1000.
# rubocop:disable Metrics/AbcSize
class ZendeskCompat::V2::SearchController < ZendeskCompat::BaseController
  SORTS = { 'created_at' => 'conversations.created_at', 'updated_at' => 'conversations.updated_at',
            'status' => 'conversations.status', 'priority' => 'conversations.priority' }.freeze
  MAX_RESULTS = 1000

  def index
    query = ZendeskCompat::SearchQuery.new(context, params[:query])
    return render_users(query) if query.type == 'user'
    raise ZendeskCompat::Error::Unsupported, "type:#{query.type} não é suportado pela busca do ServiceDesk" unless query.type == 'ticket'

    scope = query.tickets.reorder(Arel.sql("#{SORTS.fetch(params[:sort_by].to_s,
                                                          'conversations.updated_at')} #{direction}, conversations.id #{direction}"))
    records, links = paginate(scope.limit(MAX_RESULTS))
    presenter = ZendeskCompat::TicketPresenter.new(context)
    render json: { results: records.map { |c| presenter.present(c).merge(result_type: 'ticket') }, facets: nil }.merge(links)
  end

  def count
    query = ZendeskCompat::SearchQuery.new(context, params[:query])
    total = query.type == 'user' ? query.users.size : query.tickets.count
    render json: { count: total }
  end

  private

  def direction
    params[:sort_order].to_s.casecmp('asc').zero? ? 'ASC' : 'DESC'
  end

  def render_users(query)
    records, links = paginate(query.users)
    presenter = ZendeskCompat::UserPresenter.new(context)
    render json: { results: records.map { |r| presenter.present(r).merge(result_type: 'user') }, facets: nil }.merge(links)
  end
end
# rubocop:enable Metrics/AbcSize
