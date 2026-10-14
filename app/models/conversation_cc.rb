# == Schema Information
#
# Table name: conversation_ccs
#
#  id              :bigint           not null, primary key
#  email           :string           not null
#  created_at      :datetime         not null
#  updated_at      :datetime         not null
#  account_id      :bigint           not null
#  conversation_id :bigint           not null
#
# Indexes
#
#  index_conversation_ccs_on_account_id_and_email       (account_id,email)
#  index_conversation_ccs_on_conversation_id_and_email  (conversation_id,email) UNIQUE
#
# Someone copied on a ticket. Every public e-mail reply goes to the requester and to all CCs.
class ConversationCc < ApplicationRecord
  belongs_to :account
  belongs_to :conversation

  before_validation { self.email = email.to_s.strip.downcase }

  validates :email, presence: true, format: { with: Devise.email_regexp }, uniqueness: { scope: :conversation_id }
end
