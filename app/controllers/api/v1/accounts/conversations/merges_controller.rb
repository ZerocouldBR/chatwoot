# Merges this ticket (the source) into another one: POST /conversations/:conversation_id/merge
class Api::V1::Accounts::Conversations::MergesController < Api::V1::Accounts::Conversations::BaseController
  def create
    target = Current.account.conversations.find_by!(display_id: params.require(:target_id))
    authorize target, :show?
    merged = Tickets::MergeService.new(source: @conversation, target: target, user: Current.user, source_comment: params[:source_comment],
                                       target_comment: params[:target_comment], public: ActiveModel::Type::Boolean.new.cast(params[:public])).perform
    @conversation = merged
    render 'api/v1/accounts/conversations/show'
  end
end
