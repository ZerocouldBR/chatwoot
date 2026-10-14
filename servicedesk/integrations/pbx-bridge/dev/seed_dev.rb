# frozen_string_literal: true

# SÓ PARA O AMBIENTE DEV (dados FICTÍCIOS). Cria a conta de teste "Teste 55PBX (dev)", 2 times e 2 agentes.
# Depois rode o provision_55pbx.rb com ACCOUNT_ID=<id impresso> --allow-db=chatwoot_dev.
abort 'só roda no chatwoot_dev' unless ActiveRecord::Base.connection.current_database == 'chatwoot_dev'

acc = Account.find_or_create_by!(name: 'Teste 55PBX (dev)') { |a| a.locale = 'pt_BR' }
agents = [
  ['Ana Teste', 'ana.teste@exemplo.test', 'Suporte'],
  ['Bruno Fictício', 'bruno.ficticio@exemplo.test', 'Novos Negócios']
]
agents.each do |name, email, team_name|
  team = acc.teams.where('lower(name) = lower(?)', team_name).first || acc.teams.create!(name: team_name)
  u = User.from_email(email)
  unless u
    pwd = "#{SecureRandom.base64(18)}aA1!"
    u = User.new(name: name, email: email, password: pwd, password_confirmation: pwd)
    u.skip_confirmation!
    u.save!
  end
  AccountUser.find_or_create_by!(account: acc, user: u) { |au| au.role = :agent }
  TeamMember.find_or_create_by!(team: team, user: u)
end
puts "ACCOUNT_ID=#{acc.id}"
puts "TEAMS=#{acc.teams.pluck(:id, :name).inspect}"
puts "AGENTS=#{acc.users.pluck(:id, :email).inspect}"
