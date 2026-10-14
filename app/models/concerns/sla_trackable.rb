# Recomputes a ticket's SLA whenever something its policy or metrics depend on changes.
module SlaTrackable
  extend ActiveSupport::Concern

  SLA_FIELDS = %w[status priority ticket_type team_id inbox_id company_id cached_label_list].freeze

  included do
    has_one :applied_sla, dependent: :destroy
    after_create_commit :schedule_sla_update
    after_update_commit :schedule_sla_update, if: -> { saved_changes.keys.intersect?(SLA_FIELDS) }
  end

  def schedule_sla_update
    Sla::ApplyJob.perform_later(id)
  end
end
