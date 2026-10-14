# GET /api/v1/accounts/:account_id/servicedesk/views          visualizações visíveis, na ordem do Agent Workspace
# GET /api/v1/accounts/:account_id/servicedesk/views/counts   { "<id>": quantidade } (cache de 60s por escopo)
class Api::V1::Accounts::Servicedesk::ViewsController < Api::V1::Accounts::BaseController
  def index
    render json: { payload: shared_views.views }
  end

  def counts
    render json: { payload: shared_views.counts }
  end

  private

  def shared_views
    @shared_views ||= ::Servicedesk::SharedViews.new(account: Current.account, user: Current.user)
  end
end
