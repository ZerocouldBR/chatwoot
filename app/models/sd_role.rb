# == Schema Information
#
# Table name: sd_roles
#
#  id                     :bigint           not null, primary key
#  base_role              :integer          default("agent"), not null
#  description            :text
#  key                    :string           not null
#  name                   :string           not null
#  permissions            :jsonb            not null
#  position               :integer          default(0), not null
#  system                 :boolean          default(FALSE), not null
#  zendesk_configuration  :jsonb            not null
#  created_at             :datetime         not null
#  updated_at             :datetime         not null
#  account_id             :bigint           not null
#  zendesk_custom_role_id :bigint
#
# Indexes
#
#  index_sd_roles_on_account_id          (account_id)
#  index_sd_roles_on_account_id_and_key  (account_id,key) UNIQUE
#
# ServiceDesk M13: papel de agente por conta (equivalente aos papéis do Zendesk), com permissões granulares.
# Não usa custom_roles nem account_users.custom_role_id (módulo enterprise, proibido no projeto).
class SdRole < ApplicationRecord
  belongs_to :account
  has_many :account_users, dependent: :nullify

  enum :base_role, { agent: 0, administrator: 1 }, prefix: :base

  KEY_FORMAT = /\A[a-z][a-z0-9_]{1,49}\z/

  validates :key, presence: true, format: { with: KEY_FORMAT }, uniqueness: { scope: :account_id }
  validates :name, presence: true, length: { maximum: 80 }, uniqueness: { scope: :account_id }
  validate :permissions_are_known

  before_validation :normalize_permissions
  after_update_commit :sync_account_users_role, if: :saved_change_to_base_role?

  scope :ordered, -> { order(:position, :id) }

  def administrator_role?
    base_administrator?
  end

  # Permissões efetivas exibidas na tela (papel de administrador = tudo liberado, como no Zendesk).
  def effective_permissions
    return Servicedesk::Roles::Catalog::ADMIN.dup if administrator_role?

    Servicedesk::Roles::Catalog.normalize(permissions)
  end

  private

  def normalize_permissions
    @invalid_permission_keys = Servicedesk::Roles::Catalog.invalid_keys(permissions)
    base = administrator_role? ? Servicedesk::Roles::Catalog::ADMIN : Servicedesk::Roles::Catalog::CE_AGENT
    self.permissions = Servicedesk::Roles::Catalog.normalize(permissions, base: base)
    self.permissions = Servicedesk::Roles::Catalog::ADMIN.dup if administrator_role?
  end

  def permissions_are_known
    return if @invalid_permission_keys.blank?

    errors.add(:permissions, "chaves ou valores inválidos: #{@invalid_permission_keys.join(', ')}")
  end

  # Mudou a base (agente <-> administrador): os account_users com este papel acompanham.
  def sync_account_users_role
    account_users.find_each { |au| au.update!(role: base_role) }
  end
end
