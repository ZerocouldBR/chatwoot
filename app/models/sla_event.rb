# A metric of an applied SLA was breached or fulfilled.
class SlaEvent < ApplicationRecord
  belongs_to :account
  belongs_to :applied_sla
  belongs_to :conversation
  belongs_to :sla_policy
  belongs_to :inbox

  enum event_type: { breach: 0, fulfill: 1 }
end
