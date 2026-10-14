# ServiceDesk M13: quem pode ser responsável por ticket (ticket.assignable e não suspenso).
module Servicedesk::Roles::Assignable
  module_function

  # users: lista (Array ou relation) de User da conta. Devolve Array na mesma ordem, sem os não atribuíveis.
  def filter(account, users)
    users = users.to_a
    return users if users.empty?

    account_users = AccountUser.includes(:sd_role).where(account_id: account.id, user_id: users.map(&:id)).index_by(&:user_id)
    users.select { |user| account_users[user.id].nil? || account_users[user.id].sd_assignable? }
  end

  def non_assignable_user_ids(account)
    AccountUser.includes(:sd_role).where(account_id: account.id).reject(&:sd_assignable?).map(&:user_id)
  end
end
