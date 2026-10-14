# Tickets arrive as New (status 4) unless the creator sets another status.
class ChangeConversationStatusDefaultToNew < ActiveRecord::Migration[7.2]
  def change
    change_column_default :conversations, :status, from: 0, to: 4
  end
end
