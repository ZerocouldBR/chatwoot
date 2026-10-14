# Merges a ticket into another one, like Zendesk: both get a comment about the merge (private unless the agent
# makes it public), the source requester is copied on the target, and the source is closed with the
# `closed_by_merge` tag. A merge cannot be undone.
class Tickets::MergeService
  MERGE_TAG = 'closed_by_merge'.freeze
  MERGEABLE_STATUSES = Conversation::UNSOLVED_STATUSES

  pattr_initialize [:source!, :target!, :user!, :source_comment, :target_comment, :public]

  def perform
    validate!
    ActiveRecord::Base.transaction do
      comment(target, target_comment.presence || default_comment(:target_comment, source))
      comment(source, source_comment.presence || default_comment(:source_comment, target))
      copy_source_requester
      source.update!(status: :closed, merged_into_id: target.id, label_list: source.label_list | [MERGE_TAG])
    end
    target
  end

  private

  def validate!
    reason = if source.id == target.id then :same_ticket
             elsif MERGEABLE_STATUSES.exclude?(source.status) then :source_solved
             elsif target.closed? then :target_closed
             end
    raise CustomExceptions::Ticket::MergeNotAllowed, { reason: reason } if reason
  end

  def copy_source_requester
    Tickets::CcList.new(target).add(source.contact.email, author: user, via: 'agent') if source.contact_id != target.contact_id
  end

  def default_comment(key, other)
    I18n.t("tickets.merge.#{key}", id: other.display_id, subject: other.subject)
  end

  def comment(conversation, content)
    Messages::MessageBuilder.new(user, conversation, { content: content, private: !public }).perform
  end
end
