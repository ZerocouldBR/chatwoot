# ServiceDesk M13: papel SD do account_user (sd_role_id), restrição de acesso do usuário (ticket_access_override, o
# ticket_restriction do Zendesk), só comentário privado, time padrão e suspensão.
module Servicedesk::AccountUserRoles
  extend ActiveSupport::Concern

  included do
    belongs_to :sd_role, optional: true
    belongs_to :default_team, class_name: 'Team', optional: true

    validates :ticket_access_override, inclusion: { in: Servicedesk::Roles::Catalog::TICKET_ACCESS_LEVELS }, allow_nil: true
    validate :sd_role_from_same_account
    validate :default_team_from_same_account

    before_validation :normalize_ticket_access_override
    before_save :apply_sd_role_base_role, if: :will_save_change_to_sd_role_id?
    before_save :drop_sd_role_on_base_role_change, if: -> { will_save_change_to_role? && !will_save_change_to_sd_role_id? }
    after_save { @sd_access = nil }
  end

  def sd_access
    @sd_access ||= Servicedesk::Roles::Access.new(self)
  end

  def reload(*)
    @sd_access = nil
    super
  end

  def suspended?
    suspended_at.present?
  end

  # Atualização pela API de agentes (Configurações > Agentes): só as chaves enviadas mudam; null limpa.
  # suspended (bool) liga/desliga suspended_at.
  def apply_sd_role_params!(attrs)
    attrs = attrs.to_h.stringify_keys
    attrs['sd_role_id'] = account.sd_roles.find(attrs['sd_role_id']).id if attrs['sd_role_id'].present?
    if attrs.key?('suspended')
      suspend = ActiveModel::Type::Boolean.new.cast(attrs.delete('suspended'))
      attrs['suspended_at'] = suspend ? (suspended_at || Time.current) : nil
    end
    update!(attrs)
  end

  # O responsável do ticket precisa poder ser atribuído (light/colaborador não) e não estar suspenso.
  def sd_assignable?
    !suspended? && sd_access.can?('ticket.assignable')
  end

  private

  def sd_visibility_changed?
    previous_changes.keys.intersect?(%w[sd_role_id ticket_access_override suspended_at])
  end

  def normalize_ticket_access_override
    self.ticket_access_override = ticket_access_override.presence
  end

  # Escolher um papel define o papel base (agent/administrator), como no Zendesk.
  def apply_sd_role_base_role
    @sd_access = nil
    self.role = sd_role.base_role if sd_role
  end

  # O papel base mudou pela tela padrão do CE (agente <-> administrador) sem escolher papel SD: o papel SD antigo
  # deixa de valer (evita "administrador com papel Agente light").
  def drop_sd_role_on_base_role_change
    @sd_access = nil
    self.sd_role = nil if sd_role && sd_role.base_role != role
  end

  def sd_role_from_same_account
    return if sd_role.nil? || sd_role.account_id == account_id

    errors.add(:sd_role_id, 'não pertence a esta conta')
  end

  def default_team_from_same_account
    return if default_team.nil? || default_team.account_id == account_id

    errors.add(:default_team_id, 'não pertence a esta conta')
  end
end
