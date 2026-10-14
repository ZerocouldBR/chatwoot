# The SLA policy applied to a ticket, with the computed state of each measured metric.
class AppliedSla < ApplicationRecord
  belongs_to :account
  belongs_to :sla_policy
  belongs_to :conversation
  has_many :sla_events, dependent: :destroy

  enum sla_status: { active: 0, hit: 1, missed: 2 }
end
