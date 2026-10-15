# ServiceDesk M13: papéis padrão do Zendesk.
#   bundle exec rails 'servicedesk:roles:seed'            -> todas as contas (não altera papéis existentes)
#   bundle exec rails 'servicedesk:roles:seed[12,reset]'  -> só a conta 12, voltando os papéis de sistema ao padrão
namespace :servicedesk do
  namespace :roles do
    desc 'Cria os papéis padrão do Zendesk (Administrador, Agente, Agente light, Colaborador...) nas contas'
    task :seed, [:account_id, :mode] => :environment do |_task, args|
      accounts = args[:account_id].present? ? Account.where(id: args[:account_id]) : Account.all
      accounts.find_each do |account|
        roles = Servicedesk::Roles::Seeder.new(account).perform(reset: args[:mode] == 'reset')
        puts "conta #{account.id} (#{account.name}): #{roles.map(&:key).join(', ')}"
      end
    end
  end
end
