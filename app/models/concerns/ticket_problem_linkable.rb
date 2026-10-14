# Zendesk problem and incident tickets: an incident can be linked to a problem ticket, and solving the problem
# solves its unsolved incidents with the problem's last public reply. Reopening the problem leaves incidents alone.
module TicketProblemLinkable
  extend ActiveSupport::Concern

  included do
    belongs_to :problem, class_name: 'Conversation', optional: true
    has_many :incidents, class_name: 'Conversation', foreign_key: :problem_id, dependent: :nullify, inverse_of: :problem
    belongs_to :merged_into, class_name: 'Conversation', optional: true

    validate :problem_link_is_valid, if: -> { problem_id.present? && will_save_change_to_problem_id? }
    after_update_commit :solve_incidents, if: -> { saved_change_to_status? && resolved? && ticket_type_problem? }
  end

  private

  def problem_link_is_valid
    valid = ticket_type_incident? && problem&.account_id == account_id && problem&.ticket_type_problem? && problem_id != id
    errors.add(:problem_id, :invalid) unless valid
  end

  def solve_incidents
    Tickets::SolveIncidentsJob.perform_later(id)
  end
end
