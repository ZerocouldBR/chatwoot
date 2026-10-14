# ServiceDesk M13: papéis da conta (sd_roles). A conta nova já nasce com os papéis padrão do Zendesk
# (Administrador, Administrador de faturamento, Agente, Agente light, Colaborador); sem jobs nem eventos.
module Servicedesk::AccountRoles
  extend ActiveSupport::Concern

  included do
    has_many :sd_roles, dependent: :delete_all
    after_create :seed_servicedesk_roles
  end

  private

  def seed_servicedesk_roles
    Servicedesk::Roles::Seeder.new(self).perform
  end
end
