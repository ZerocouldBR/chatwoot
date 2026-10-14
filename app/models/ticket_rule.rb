# Zendesk triggers and automations.
# - Triggers run, in order, on every ticket update; each fires at most once per update and the list restarts after one fires.
# - Automations run hourly on time-based conditions and must nullify themselves so they act once per ticket.
# Conditions: { all: [{ field, operator, value, business_hours? }], any: [...] }; actions: [{ field, value }].
# == Schema Information
#
# Table name: ticket_rules
#
#  id          :bigint           not null, primary key
#  actions     :jsonb            not null
#  active      :boolean          default(TRUE), not null
#  conditions  :jsonb            not null
#  description :string
#  kind        :integer          not null
#  position    :integer          default(0), not null
#  title       :string           not null
#  created_at  :datetime         not null
#  updated_at  :datetime         not null
#  account_id  :bigint           not null
#
# Indexes
#
#  index_ticket_rules_on_account_id                        (account_id)
#  index_ticket_rules_on_account_id_and_kind_and_position  (account_id,kind,position)
#
class TicketRule < ApplicationRecord
  ACTION_FIELDS = %w[status priority ticket_type team_id assignee_id add_tags remove_tags set_tags add_cc add_follower
                     email_requester email_requester_and_ccs email_assignee email_group email_user notify_webhook].freeze
  EMAIL_ACTIONS = %w[email_requester email_requester_and_ccs email_assignee email_group email_user].freeze

  belongs_to :account

  # Prefixed: Active Record already defines `trigger` and `triggers` class methods.
  enum kind: { trigger: 0, automation: 1 }, _prefix: true

  validates :title, presence: true
  validate :conditions_are_valid
  validate :actions_are_valid
  validate :automation_is_time_based_and_nullified, if: :kind_automation?
  validate :business_hours_need_a_schedule
  validate :triggers_cannot_close, if: :kind_trigger?

  scope :ordered, -> { order(:position, :id) }
  scope :active, -> { where(active: true) }

  def matches?(conversation, update: nil, now: Time.current)
    Tickets::Rules::Conditions.new(conditions, conversation, update: update, now: now).match?
  end

  private

  def condition_list
    conditions.values_at('all', 'any').flatten.compact
  end

  def conditions_are_valid
    allowed = Tickets::Rules::Conditions.fields_for(kind)
    valid = conditions.is_a?(Hash) && condition_list.any? && condition_list.all? do |condition|
      allowed.include?(condition['field']) && Tickets::Rules::Conditions.operators_for(condition['field'], kind).include?(condition['operator'])
    end
    errors.add(:conditions, :invalid) unless valid
  end

  def actions_are_valid
    valid = actions.is_a?(Array) && actions.any? && actions.all? { |action| ACTION_FIELDS.include?(action['field']) }
    errors.add(:actions, :invalid) unless valid
  end

  # Zendesk rejects automations that could run on the same ticket every hour: they need a time condition, and either an
  # "is" hours condition (true for a single hour) or an action that makes one of the conditions false.
  def automation_is_time_based_and_nullified
    time_conditions = condition_list.select { |condition| condition['field'].start_with?('hours_') }
    return errors.add(:conditions, I18n.t('errors.ticket_rules.needs_time_condition')) if time_conditions.empty?
    return if time_conditions.any? { |condition| condition['operator'] == 'is' }
    return if condition_list.any? { |condition| nullified?(condition) }

    errors.add(:actions, I18n.t('errors.ticket_rules.needs_nullifying_action'))
  end

  def nullified?(condition)
    actions.any? { |action| nullifies?(condition, action) }
  end

  def nullifies?(condition, action)
    field, operator, value = condition.values_at('field', 'operator', 'value')
    return tags_nullify?(operator, value.to_s.split, action) if field == 'labels'
    return false unless action['field'] == field

    operator == 'is' ? action['value'].to_s != value.to_s : operator == 'is_not' && action['value'].to_s == value.to_s
  end

  def tags_nullify?(operator, tags, action)
    action_tags = action['value'].to_s.split
    case action['field']
    when 'remove_tags' then operator == 'includes' && action_tags.intersect?(tags)
    when 'add_tags' then operator == 'not_includes' && action_tags.intersect?(tags)
    when 'set_tags' then action_tags.intersect?(tags) == (operator == 'not_includes')
    else false
    end
  end

  # Only automations close tickets: Zendesk triggers cannot set Closed.
  def triggers_cannot_close
    errors.add(:actions, :invalid) if actions.any? { |action| action['field'] == 'status' && action['value'] == 'closed' }
  end

  def business_hours_need_a_schedule
    return unless condition_list.any? { |condition| condition['business_hours'] } && BusinessSchedule.default_for(account).nil?

    errors.add(:conditions, I18n.t('errors.ticket_rules.business_hours_need_schedule'))
  end
end
