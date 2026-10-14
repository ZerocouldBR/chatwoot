# GET /api/v2/tickets/:ticket_id/comments(.json) com include=users, sort_order=asc|desc, page/per_page.
class ZendeskCompat::V2::TicketCommentsController < ZendeskCompat::BaseController
  def index
    conversation = find_ticket!
    direction = params[:sort_order].to_s.casecmp('desc').zero? ? :desc : :asc
    scope = ZendeskCompat::CommentPresenter.comment_scope(conversation).reorder(created_at: direction, id: direction)
    messages, links = paginate(scope)
    presenter = ZendeskCompat::CommentPresenter.new(context)
    comments = messages.map { |message| presenter.present(message) }
    payload = { comments: comments }.merge(links)
    payload[:users] = users_for(comments) if params[:include].to_s.split(',').include?('users')
    render json: payload
  end

  private

  def users_for(comments)
    presenter = ZendeskCompat::UserPresenter.new(context)
    context.directory.actors(comments.pluck(:author_id).uniq).map { |record| presenter.present(record) }
  end
end
