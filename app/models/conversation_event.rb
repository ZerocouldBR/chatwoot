# == Schema Information
#
# Table name: conversation_events
#
#  id              :bigint           not null, primary key
#  author_type     :string
#  event_type      :string           not null
#  field_name      :string
#  previous_value  :jsonb
#  value           :jsonb
#  via             :string           not null
#  created_at      :datetime         not null
#  account_id      :bigint           not null
#  author_id       :bigint
#  conversation_id :bigint           not null
#
# Indexes
#
#  index_conversation_events_on_account_id_and_created_at  (account_id,created_at)
#  index_conversation_events_on_conversation_id_and_id     (conversation_id,id)
#
# Append-only audit trail of a ticket: what changed, who changed it and through which path.
class ConversationEvent < ApplicationRecord
  EVENT_TYPES = %w[create change comment redaction].freeze
  VIAS = %w[agent customer rule bot system].freeze

  belongs_to :account
  belongs_to :conversation
  belongs_to :author, polymorphic: true, optional: true

  validates :event_type, inclusion: { in: EVENT_TYPES }
  validates :via, inclusion: { in: VIAS }

  before_update { raise ActiveRecord::ReadOnlyRecord }
end
