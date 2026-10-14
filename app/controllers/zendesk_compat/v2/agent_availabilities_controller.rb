# GET /api/v2/agent_availabilities?filter[group_id]=N (formato JSON:API do Omnichannel Routing do Zendesk).
# Status: disponibilidade do agente na conta (online -> Online, busy -> Away, offline -> Offline), Offline sem presença.
# Canais support/messaging/talk: work_item_count = conversas abertas atribuídas ao agente nas caixas daquele canal;
# max_capacity = ZENDESK_COMPAT_MAX_CAPACITY (padrão 20).
class ZendeskCompat::V2::AgentAvailabilitiesController < ZendeskCompat::BaseController
  STATUS_NAMES = { 'online' => 'Online', 'busy' => 'Away', 'offline' => 'Offline' }.freeze
  CHANNELS = {
    'support' => %w[Channel::Email Channel::Api], 'messaging' => %w[Channel::Whatsapp Channel::WebWidget Channel::FacebookPage
                                                                    Channel::Instagram Channel::Telegram Channel::Line Channel::Sms
                                                                    Channel::TwilioSms],
    'talk' => %w[Channel::Voice]
  }.freeze

  def index
    users = agents
    counts = work_counts(users.map(&:id))
    render json: {
      data: users.map { |user| agent_json(user) }, included: users.flat_map { |user| channel_json(user, counts) },
      links: { first: nil, last: nil, next: nil, prev: nil }, meta: { has_more: false, after_cursor: nil, before_cursor: nil }
    }
  end

  private

  def agents
    group_id = params.dig(:filter, :group_id)
    scope = current_account.users
    return scope.order(:id).to_a if group_id.blank?

    team = context.directory.team(group_id) || raise(ZendeskCompat::Error::NotFound)
    scope.where(id: team.team_members.select(:user_id)).order(:id).to_a
  end

  def status_name(user)
    availability = OnlineStatusTracker.get_presence(current_account.id, 'User', user.id) ? context.account_user(user)&.availability : 'offline'
    STATUS_NAMES.fetch(availability.to_s, 'Offline')
  end

  def agent_json(user)
    zid = ZendeskCompat::Ids.user_id(user)
    {
      type: 'agent_availabilities', id: zid.to_s,
      attributes: { agent_id: zid, version: 1, agent_status: { id: status_name(user).downcase, name: status_name(user), updated_at: nil },
                    updated_at: nil },
      relationships: { channels: { data: CHANNELS.keys.map { |channel| { type: 'channels', id: channel_id(zid, channel) } } } }
    }
  end

  def channel_json(user, counts)
    zid = ZendeskCompat::Ids.user_id(user)
    CHANNELS.keys.map do |channel|
      { type: 'channels', id: channel_id(zid, channel),
        attributes: { name: channel, status: status_name(user).downcase, updated_at: nil, max_capacity: max_capacity,
                      work_item_count: counts.fetch([user.id, channel], 0) } }
    end
  end

  def channel_id(zid, channel)
    "agent_availabilities|#{zid}|channels|#{channel}"
  end

  def work_counts(user_ids)
    rows = current_account.conversations.open.where(assignee_id: user_ids).joins(:inbox).group(:assignee_id, 'inboxes.channel_type').count
    rows.each_with_object(Hash.new(0)) do |((user_id, channel_type), total), memo|
      channel = CHANNELS.find { |_name, types| types.include?(channel_type) }&.first || 'support'
      memo[[user_id, channel]] += total
    end
  end

  def max_capacity
    ENV.fetch('ZENDESK_COMPAT_MAX_CAPACITY', 20).to_i
  end
end
