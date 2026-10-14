# == Schema Information
#
# Table name: teams
#
#  id                :bigint           not null, primary key
#  allow_auto_assign :boolean          default(TRUE)
#  description       :text
#  icon              :string           default("")
#  icon_color        :string           default("")
#  name              :string           not null
#  created_at        :datetime         not null
#  updated_at        :datetime         not null
#  account_id        :bigint           not null
#
# Indexes
#
#  index_teams_on_account_id                 (account_id)
#  index_teams_on_account_id_and_lower_name  (account_id, lower((name)::text)) UNIQUE
#
class Team < ApplicationRecord
  include AccountCacheRevalidator

  belongs_to :account
  has_many :team_members, dependent: :destroy_async
  has_many :members, through: :team_members, source: :user
  has_many :conversations, dependent: :nullify

  before_destroy :capture_filtered_unread_count_member_ids, prepend: true
  after_destroy_commit :invalidate_filtered_unread_counts_after_destroy

  validates :name,
            presence: { message: I18n.t('errors.validations.presence') },
            uniqueness: { scope: :account_id, case_sensitive: false }

  # ServiceDesk: o nome fica como foi digitado (maiúsculas e acentos, como os
  # grupos do sistema anterior). A unicidade continua sem diferenciar maiúsculas,
  # pela validação acima e pelo índice único em lower(name).
  before_validation do
    self.name = name.gsub(/[[:cntrl:]]/, '').strip if attribute_present?('name')
  end

  # Adds multiple members to the team
  # @param user_ids [Array<Integer>] Array of user IDs to add as members
  # @return [Array<User>] Array of newly added members
  def add_members(user_ids)
    team_members_to_create = user_ids.map { |user_id| { user_id: user_id } }
    created_members = team_members.create(team_members_to_create)
    added_users = created_members.filter_map(&:user)

    update_account_cache
    added_users
  end

  # Removes multiple members from the team
  # @param user_ids [Array<Integer>] Array of user IDs to remove
  # @return [void]
  def remove_members(user_ids)
    team_members.where(user_id: user_ids).destroy_all
    update_account_cache
  end

  def messages
    account.messages.where(conversation_id: conversations.pluck(:id))
  end

  def reporting_events
    account.reporting_events.where(conversation_id: conversations.pluck(:id))
  end

  def push_event_data
    {
      id: id,
      name: name,
      icon: icon,
      icon_color: icon_color
    }
  end

  private

  def capture_filtered_unread_count_member_ids
    @filtered_unread_count_member_ids = team_members.pluck(:user_id)
  end

  def invalidate_filtered_unread_counts_after_destroy
    invalidator = ::Conversations::UnreadCounts::FilteredCountInvalidator.new(account)
    invalidator.conversation_changed!
    invalidator.users_visibility_changed!(user_ids: @filtered_unread_count_member_ids)
  end
end

Team.include_mod_with('Audit::Team')
