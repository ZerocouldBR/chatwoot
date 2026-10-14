class Conversations::SortService
  DEFAULT_SORT = 'last_activity_at_desc'.freeze
  SORT_OPTIONS = {
    'last_activity_at_asc' => %w[sort_on_last_activity_at asc],
    'last_activity_at_desc' => %w[sort_on_last_activity_at desc],
    'created_at_asc' => %w[sort_on_created_at asc],
    'created_at_desc' => %w[sort_on_created_at desc],
    'priority_asc' => %w[sort_on_priority asc],
    'priority_desc' => %w[sort_on_priority desc],
    'waiting_since_asc' => %w[sort_on_waiting_since asc],
    'waiting_since_desc' => %w[sort_on_waiting_since desc],
    'priority_desc_created_at_asc' => %w[sort_on_priority_created_at desc],
    'unread' => %w[sort_on_unread desc],
    # ServiceDesk: ordenações das views do Zendesk (Servicedesk::ConversationViewSorts)
    'sd_sla_asc' => %w[sort_on_sd_next_sla_breach_at asc],
    'sd_sla_desc' => %w[sort_on_sd_next_sla_breach_at desc],
    'sd_id_asc' => %w[sort_on_sd_display_id asc],
    'sd_id_desc' => %w[sort_on_sd_display_id desc],
    'sd_subject_asc' => %w[sort_on_sd_subject asc],
    'sd_subject_desc' => %w[sort_on_sd_subject desc],
    'sd_group_asc' => %w[sort_on_sd_team_name asc],
    'sd_group_desc' => %w[sort_on_sd_team_name desc],
    'sd_requester_asc' => %w[sort_on_sd_requester_name asc],
    'sd_requester_desc' => %w[sort_on_sd_requester_name desc],
    'sd_assignee_asc' => %w[sort_on_sd_assignee_name asc],
    'sd_assignee_desc' => %w[sort_on_sd_assignee_name desc],
    'sd_channel_asc' => %w[sort_on_sd_inbox_name asc],
    'sd_channel_desc' => %w[sort_on_sd_inbox_name desc],
    'sd_status_asc' => %w[sort_on_sd_status_category asc],
    'sd_status_desc' => %w[sort_on_sd_status_category desc],
    'sd_solved_asc' => %w[sort_on_sd_solved_at asc],
    'sd_solved_desc' => %w[sort_on_sd_solved_at desc],
    'sd_requester_updated_asc' => %w[sort_on_sd_requester_updated_at asc],
    'sd_requester_updated_desc' => %w[sort_on_sd_requester_updated_at desc],
    'sd_assignee_updated_asc' => %w[sort_on_sd_assignee_updated_at asc],
    'sd_assignee_updated_desc' => %w[sort_on_sd_assignee_updated_at desc],

    # To be removed in v3.5.0
    'latest' => %w[sort_on_last_activity_at desc],
    'sort_on_created_at' => %w[sort_on_created_at asc],
    'sort_on_priority' => %w[sort_on_priority desc],
    'sort_on_waiting_since' => %w[sort_on_waiting_since asc]
  }.with_indifferent_access.freeze

  def self.apply(scope, sort_by)
    sort_method, sort_order = SORT_OPTIONS[sort_by] || SORT_OPTIONS[DEFAULT_SORT]
    scope.public_send(sort_method, sort_order)
  end
end
