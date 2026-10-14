# /api/v2/tickets/:ticket_id/tags(.json) com a semântica do Zendesk:
#   GET lista | POST substitui (set tags) | PUT acrescenta (add tags) | DELETE remove. Corpo: {"tags": [...]}.
class ZendeskCompat::V2::TicketTagsController < ZendeskCompat::BaseController
  def index
    render json: { tags: find_ticket!.label_list.sort }
  end

  def create
    update_tags { |_current, tags| tags }
  end

  def update
    update_tags { |current, tags| current | tags }
  end

  def destroy
    update_tags { |current, tags| current - tags }
  end

  private

  def update_tags
    conversation = find_ticket!
    tags = ZendeskCompat::Tags.normalize(body_params['tags'] || params[:tags])
    labels = yield(conversation.label_list.to_a, tags)
    conversation.update!(label_list: labels) if labels.sort != conversation.label_list.to_a.sort
    render json: { tags: conversation.reload.label_list.sort }
  end
end
