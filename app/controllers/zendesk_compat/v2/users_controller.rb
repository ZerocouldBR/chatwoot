# /api/v2/users: show, show_many (ids=1,2,3), search (query= ou email=) e me.
# rubocop:disable Metrics/AbcSize
class ZendeskCompat::V2::UsersController < ZendeskCompat::BaseController
  def show
    record = context.directory.actor(params[:id]) || raise(ZendeskCompat::Error::NotFound)
    render json: { user: presenter.present(record) }
  end

  def show_many
    ids = params[:ids].to_s.split(',').map(&:strip).compact_blank.first(100)
    records = ids.filter_map { |id| context.directory.actor(id) }.uniq
    render json: { users: records.map { |record| presenter.present(record) }, next_page: nil, previous_page: nil, count: records.size }
  end

  def search
    records = if params[:email].present?
                [context.directory.actor_by_email(params[:email])].compact
              elsif params[:external_id].present?
                current_account.contacts.where("additional_attributes->'zendesk'->>'external_id' = ?", params[:external_id].to_s).to_a
              else
                ZendeskCompat::SearchQuery.new(context, params[:query]).users
              end
    page, links = paginate(records)
    render json: { users: page.map { |record| presenter.present(record) } }.merge(links)
  end

  def me
    render json: { user: presenter.present(context.user) }
  end

  private

  def presenter
    @presenter ||= ZendeskCompat::UserPresenter.new(context)
  end
end
# rubocop:enable Metrics/AbcSize
