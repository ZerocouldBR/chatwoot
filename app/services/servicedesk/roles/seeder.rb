# ServiceDesk M13: cria os papéis padrão do Zendesk numa conta (idempotente).
# Papel que já existe (mesma key) não é alterado: o administrador pode ter editado as permissões na tela "Papéis".
# Use reset: true para voltar um papel de sistema ao padrão.
class Servicedesk::Roles::Seeder
  def initialize(account)
    @account = account
  end

  def perform(reset: false)
    Servicedesk::Roles::Defaults::ROLES.map do |key, attrs|
      role = SdRole.find_or_initialize_by(account_id: @account.id, key: key)
      next role if role.persisted? && !reset

      role.assign_attributes(
        name: attrs[:name], description: attrs[:description], base_role: attrs[:base_role],
        permissions: attrs[:permissions], zendesk_custom_role_id: attrs[:zendesk_custom_role_id],
        position: attrs[:position], system: true
      )
      role.save! if role.changed?
      role
    end
  end
end
