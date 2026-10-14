# Zendesk-style SLA policy: tickets matching its conditions (first match by position) get per-priority
# targets for up to seven metrics, each measured in calendar or business hours.
# == Schema Information
#
# Table name: sla_policies
#
#  id          :bigint           not null, primary key
#  description :string
#  filter      :jsonb            not null
#  name        :string           not null
#  position    :integer          default(0), not null
#  targets     :jsonb            not null
#  created_at  :datetime         not null
#  updated_at  :datetime         not null
#  account_id  :bigint           not null
#
# Indexes
#
#  index_sla_policies_on_account_id  (account_id)
#
class SlaPolicy < ApplicationRecord
  METRICS = %w[first_reply_time next_reply_time periodic_update pausable_update requester_wait_time agent_work_time
               total_resolution_time].freeze
  PRIORITIES = %w[urgent high medium low].freeze
  BOOLEANS = [true, false].freeze

  belongs_to :account
  has_many :applied_slas, dependent: :destroy

  validates :name, presence: true
  validate :targets_are_valid
  validate :filter_is_valid
  validate :business_hours_need_a_schedule

  scope :ordered, -> { order(:position, :id) }

  after_commit -> { Sla::ReapplyAccountJob.perform_later(account_id) }

  # Target for a metric at a priority, or nil when the policy does not measure it.
  def target_for(metric, priority)
    targets.find { |target| target['metric'] == metric && target['priority'] == priority }
  end

  def matches?(conversation)
    Tickets::Rules::Conditions.new(filter, conversation).match?
  end

  private

  def targets_are_valid
    unique = targets.map { |target| target.values_at('metric', 'priority') }.uniq.size == targets.size
    errors.add(:targets, :invalid) unless unique && targets.all? { |target| valid_target?(target) }
  end

  def valid_target?(target)
    METRICS.include?(target['metric']) && PRIORITIES.include?(target['priority']) && target['minutes'].is_a?(Integer) &&
      target['minutes'].positive? && BOOLEANS.include?(target['business_hours'])
  end

  def filter_is_valid
    conditions = filter.fetch('all', []) + filter.fetch('any', [])
    valid = conditions.all? do |condition|
      Tickets::Rules::Conditions.fields_for('sla').include?(condition['field']) &&
        Tickets::Rules::Conditions.operators_for(condition['field'], 'sla').include?(condition['operator'])
    end
    errors.add(:filter, :invalid) unless valid
  end

  def business_hours_need_a_schedule
    return unless targets.any? { |target| target['business_hours'] } && BusinessSchedule.default_for(account).nil?

    errors.add(:targets, I18n.t('errors.sla.business_hours_need_schedule'))
  end
end
