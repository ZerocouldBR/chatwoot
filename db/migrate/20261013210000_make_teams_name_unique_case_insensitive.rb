# ServiceDesk (M1): nomes de time com maiúsculas e acentos.
# O model deixa de forçar minúsculas; a unicidade por conta passa a ser
# case-insensitive no banco (índice único em lower(name)).
# Os nomes atuais estão todos em minúsculas, então não há conflito ao criar o
# índice. O down volta ao índice antigo (case-sensitive) sem mexer nos dados.
class MakeTeamsNameUniqueCaseInsensitive < ActiveRecord::Migration[7.1]
  OLD_INDEX = 'index_teams_on_name_and_account_id'.freeze
  NEW_INDEX = 'index_teams_on_account_id_and_lower_name'.freeze

  def up
    remove_index :teams, name: OLD_INDEX, if_exists: true
    add_index :teams, 'account_id, lower(name)', unique: true, name: NEW_INDEX
  end

  def down
    remove_index :teams, name: NEW_INDEX, if_exists: true
    add_index :teams, [:name, :account_id], unique: true, name: OLD_INDEX
  end
end
