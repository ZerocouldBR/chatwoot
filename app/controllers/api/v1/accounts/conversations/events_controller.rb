# Ticket audit trail, newest first, paginated with a `before` event id cursor.
class Api::V1::Accounts::Conversations::EventsController < Api::V1::Accounts::Conversations::BaseController
  PER_PAGE = 50

  def index
    scope = @conversation.conversation_events.includes(:author).order(id: :desc)
    scope = scope.where('id < ?', params[:before]) if params[:before].present?
    @events = scope.limit(PER_PAGE).to_a
    @labels = id_field_labels(@events)
  end

  private

  ID_FIELDS = { 'assignee_id' => :users, 'team_id' => :teams, 'company_id' => :companies, 'contact_id' => :contacts }.freeze

  # Display names for fields stored as ids, so the client does not need one lookup per event.
  def id_field_labels(events)
    ID_FIELDS.to_h do |field, association|
      ids = events.select { |event| event.field_name == field }.flat_map { |event| [event.previous_value, event.value] }.compact.uniq
      [field, Current.account.public_send(association).where(id: ids).pluck(:id, :name).to_h]
    end
  end
end
