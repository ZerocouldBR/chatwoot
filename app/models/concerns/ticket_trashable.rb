# Deleted tickets go to the trash (Zendesk "Deleted tickets"): hidden everywhere, restorable for 30 days and then
# purged for good. Trashed tickets are only reachable through `trashed`.
module TicketTrashable
  extend ActiveSupport::Concern

  TRASH_RETENTION = 30.days

  included do
    default_scope { where(deleted_at: nil) }
    scope :trashed, -> { unscope(where: :deleted_at).where.not(deleted_at: nil) }
  end

  def trash!
    update!(deleted_at: Time.current)
  end

  def restore!
    update!(deleted_at: nil)
  end
end
