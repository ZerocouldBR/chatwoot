# == Schema Information
#
# Table name: portal_user_segments
#
#  id          :bigint           not null, primary key
#  company_ids :bigint           default([]), not null, is an Array
#  contact_ids :bigint           default([]), not null, is an Array
#  name        :string           not null
#  or_tags     :string           default([]), not null, is an Array
#  tags        :string           default([]), not null, is an Array
#  user_type   :integer          default("signed_in"), not null
#  created_at  :datetime         not null
#  updated_at  :datetime         not null
#  account_id  :bigint           not null
#  external_id :string
#  portal_id   :bigint           not null
#
# Indexes
#
#  index_portal_user_segments_on_account_id                 (account_id)
#  index_portal_user_segments_on_portal_id                  (portal_id)
#  index_portal_user_segments_on_portal_id_and_external_id  (portal_id,external_id) UNIQUE WHERE (external_id IS NOT NULL)
#
# ServiceDesk B2B: segmento de usuário da Central de Ajuda, equivalente ao "user segment" do Zendesk Guide.
#
# Regras (iguais às do Zendesk):
# - signed_in: qualquer contato logado no portal, restrito ainda por organização (company_ids), tags
#   (todas obrigatórias), or_tags (pelo menos uma) e contatos avulsos (contact_ids, "added_user_ids").
#   Quando há organização e tags, o contato precisa atender às duas condições.
# - staff: só a equipe. Nunca aparece no portal; o artigo continua acessível aos agentes no painel.
#
# As tags do Zendesk correspondem às etiquetas (labels) do contato.
class PortalUserSegment < ApplicationRecord
  belongs_to :account
  belongs_to :portal
  has_many :articles, dependent: :nullify

  enum :user_type, { signed_in: 0, staff: 1 }

  validates :name, presence: true
  validate :portal_belongs_to_account

  before_validation :normalize_lists

  # IDs dos segmentos do portal que o contato pode ver. Anônimo (nil) não vê nenhum segmento.
  def self.visible_ids_for(portal, contact)
    return [] if contact.blank? || portal.blank? || contact.account_id != portal.account_id

    labels = contact.label_list.map { |label| label.to_s.downcase }
    where(portal_id: portal.id).signed_in.select { |segment| segment.matches?(contact, labels) }.map(&:id)
  end

  def matches?(contact, labels = nil)
    return false unless eligible?(contact)
    return true if contact_ids.include?(contact.id)

    labels ||= contact.label_list.map { |label| label.to_s.downcase }
    company_match?(contact) && tags_match?(labels)
  end

  private

  def eligible?(contact)
    signed_in? && contact.present? && contact.account_id == account_id
  end

  def company_match?(contact)
    company_ids.blank? || company_ids.include?(contact.company_id)
  end

  def tags_match?(labels)
    (tags - labels).empty? && (or_tags.blank? || or_tags.intersect?(labels))
  end

  def normalize_lists
    self.tags = normalize_tags(tags)
    self.or_tags = normalize_tags(or_tags)
    self.company_ids = normalize_ids(company_ids)
    self.contact_ids = normalize_ids(contact_ids)
  end

  def normalize_tags(list)
    Array(list).compact_blank.map { |tag| tag.to_s.downcase.strip }.uniq
  end

  def normalize_ids(list)
    Array(list).compact_blank.map(&:to_i).uniq
  end

  def portal_belongs_to_account
    errors.add(:portal, 'must belong to the same account') if portal && account_id && portal.account_id != account_id
  end
end
