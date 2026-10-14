# /api/v2/groups (times): index, show, memberships e users. id do grupo = id do Zendesk (config) ou teams.id.
class ZendeskCompat::V2::GroupsController < ZendeskCompat::BaseController
  def index
    teams, links = paginate(current_account.teams.order(:id))
    render json: { groups: teams.map { |team| group_json(team) } }.merge(links)
  end

  def show
    render json: { group: group_json(find_team!) }
  end

  def memberships
    team = find_team!
    members, links = paginate(team.team_members.includes(:user).order(:id))
    render json: { group_memberships: members.map { |member| membership_json(team, member) } }.merge(links)
  end

  def users
    members, links = paginate(find_team!.team_members.includes(:user).order(:id))
    presenter = ZendeskCompat::UserPresenter.new(context)
    render json: { users: members.filter_map { |member| member.user && presenter.present(member.user) } }.merge(links)
  end

  private

  def find_team!
    context.directory.team(params[:group_id] || params[:id]) || raise(ZendeskCompat::Error::NotFound)
  end

  def group_json(team)
    id = context.directory.group_id(team)
    {
      id: id, url: context.api_url("groups/#{id}.json"), name: team.name, description: team.description.to_s, default: false,
      deleted: false, is_public: true, created_at: context.time(team.created_at), updated_at: context.time(team.updated_at)
    }
  end

  def membership_json(team, member)
    {
      id: member.id, url: context.api_url("group_memberships/#{member.id}.json"), user_id: ZendeskCompat::Ids.user_id(member.user),
      group_id: context.directory.group_id(team), default: false, created_at: context.time(member.created_at),
      updated_at: context.time(member.updated_at)
    }
  end
end
