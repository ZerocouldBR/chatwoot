class V2::Reports::ChannelSummaryBuilder
  include DateRangeHelper

  pattr_initialize [:account!, :params!]

  def build
    conversations_by_channel_and_status.transform_values { |status_counts| build_channel_stats(status_counts) }
  end

  private

  def conversations_by_channel_and_status
    account.conversations
           .joins(:inbox)
           .where(created_at: range)
           .group('inboxes.channel_type', 'conversations.status')
           .count
           .each_with_object({}) do |((channel_type, status), count), grouped|
      grouped[channel_type] ||= {}
      grouped[channel_type][status] = count
    end
  end

  def build_channel_stats(status_counts)
    stats = Conversation.statuses.keys.to_h { |status| [status.to_sym, status_counts[status] || 0] }
    stats.merge(total: stats.values.sum)
  end
end
