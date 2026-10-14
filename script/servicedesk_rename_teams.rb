# ServiceDesk: devolve aos times os nomes originais dos grupos do sistema
# anterior (maiúsculas e acentos), a partir do groups.json da exportação.
#
# Pré-requisito: a imagem do fork com a migração
# 20261013210000_make_teams_name_unique_case_insensitive (o Team não força mais
# minúsculas). Na imagem oficial do Chatwoot o nome volta a ser salvo em
# minúsculas e o script não tem efeito.
#
# Uso (dry-run por padrão; nada é gravado sem APPLY=1):
#   bundle exec rails runner script/servicedesk_rename_teams.rb /caminho/groups.json <account_id>
#   APPLY=1 bundle exec rails runner script/servicedesk_rename_teams.rb /caminho/groups.json <account_id>
#
# Casamento: time cujo lower(name) é igual ao nome do grupo em minúsculas (como
# o Chatwoot salvou na provisão). Grupos excluídos (deleted=true) são ignorados.
# Idempotente: times já com o nome original não mudam.
require 'json'

# rubocop:disable Rails/Output -- script de console: o relatório vai para o stdout de propósito

path, account_id = ARGV
abort 'uso: rails runner script/servicedesk_rename_teams.rb <groups.json> <account_id>' if path.blank? || account_id.blank?

apply = ENV['APPLY'] == '1'
account = Account.find(account_id)
raw = JSON.parse(File.read(path))
groups = raw.is_a?(Hash) ? raw.fetch('groups', []) : raw
normalize = ->(name) { name.to_s.gsub(/[[:cntrl:]]/, '').strip }

stats = Hash.new(0)
groups.each do |group|
  next stats[:ignorados_excluidos] += 1 if group['deleted']

  original = normalize.call(group['name'])
  next stats[:ignorados_sem_nome] += 1 if original.blank?

  team = account.teams.find_by('LOWER(name) = ?', original.downcase)
  if team.nil?
    stats[:sem_time] += 1
    puts "SEM TIME  #{original}"
  elsif team.name == original
    stats[:ja_ok] += 1
  else
    stats[:renomear] += 1
    puts "#{apply ? 'RENOMEADO' : 'RENOMEAR '} #{team.id}: #{team.name.inspect} -> #{original.inspect}"
    team.update!(name: original) if apply
  end
end

puts "conta=#{account.id} modo=#{apply ? 'APPLY' : 'DRY-RUN'} #{stats.map { |k, v| "#{k}=#{v}" }.join(' ')}"
puts 'RENAME_TEAMS_OK'
# rubocop:enable Rails/Output
