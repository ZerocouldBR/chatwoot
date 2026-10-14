# GET /api/v2/tickets/:ticket_id/audits(.json): paginação por cursor (page[size], page[after], page[before]) com
# meta.has_more e links.next, ou por offset (page/per_page) com next_page — os dois formatos do Zendesk.
# rubocop:disable Metrics/AbcSize, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
class ZendeskCompat::V2::TicketAuditsController < ZendeskCompat::BaseController
  def index
    audits = ZendeskCompat::AuditsBuilder.new(context, find_ticket!).audits
    audits = audits.reverse if params[:sort_order].to_s.casecmp('desc').zero?
    return render json: cursor_page(audits) if cursor_params.present? || params[:page].blank?

    records, links = paginate(audits)
    render json: { audits: records }.merge(links)
  end

  private

  def cursor_params
    params[:page].is_a?(ActionController::Parameters) ? params[:page] : nil
  end

  def cursor_page(audits)
    size = (cursor_params&.dig(:size) || params[:per_page] || PER_PAGE_DEFAULT).to_i.clamp(1, PER_PAGE_MAX)
    start = decode_cursor(cursor_params&.dig(:after)) || 0
    start = [decode_cursor(cursor_params&.dig(:before)).to_i - size, 0].max if cursor_params&.dig(:before).present?
    records = audits[start, size] || []
    has_more = start + size < audits.size
    {
      audits: records,
      meta: { has_more: has_more, after_cursor: has_more ? encode_cursor(start + size) : nil,
              before_cursor: start.positive? ? encode_cursor(start) : nil },
      links: { next: has_more ? cursor_url(after: encode_cursor(start + size), size: size) : nil,
               prev: start.positive? ? cursor_url(before: encode_cursor(start), size: size) : nil }
    }
  end

  def encode_cursor(offset)
    Base64.urlsafe_encode64("o:#{offset}", padding: false)
  end

  def decode_cursor(cursor)
    return if cursor.blank?

    Base64.urlsafe_decode64(cursor.to_s).delete_prefix('o:').to_i
  rescue ArgumentError
    raise ZendeskCompat::Error, 'Cursor inválido'
  end

  def cursor_url(cursor)
    query = request.query_parameters.except('page').merge('page' => cursor.stringify_keys)
    "#{request.base_url}#{request.path}?#{query.to_query}"
  end
end
# rubocop:enable Metrics/AbcSize, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
