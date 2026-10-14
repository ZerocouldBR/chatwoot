# Resolve IDs do Zendesk (ZendeskCompat::Ids) para registros da conta: usuários (agente, bot ou contato),
# organizações e grupos (times). Só devolve registros ligados à conta.
class ZendeskCompat::Directory
  attr_reader :account

  def initialize(account)
    @account = account
    @cache = {}
  end

  # Agente, bot ou contato pelo id do Zendesk. Agente/bot com o mesmo id de origem de um contato vencem
  # (o agente importado também tem um contato zd:<id>, decisão 6 da importação).
  def actor(id)
    zid = ZendeskCompat::Ids.integer(id)
    return if zid.nil? || zid <= 0

    @cache[[:actor, zid]] ||= find_actor(zid)
  end

  def actors(ids)
    Array(ids).filter_map { |id| actor(id) }.uniq
  end

  # Agente (User) com acesso à conta; usado em atribuições.
  def agent(id)
    record = actor(id)
    record.is_a?(User) && account.users.exists?(record.id) ? record : nil
  end

  def agent_by_email(email)
    return if email.blank?

    account.users.from_email(email.to_s.strip.downcase)
  end

  def contact_by_email(email)
    return if email.blank?

    account.contacts.from_email(email.to_s.strip.downcase)
  end

  def actor_by_email(email)
    agent_by_email(email) || contact_by_email(email)
  end

  def team(group_id)
    gid = ZendeskCompat::Ids.integer(group_id)
    return if gid.nil?

    @cache[[:team, gid]] ||= begin
      mapped = ZendeskCompat::Config.groups[gid.to_s]
      name = mapped && (mapped['team_name'] || mapped['name'])
      (name && account.teams.where('LOWER(name) = ?', name.downcase).first) || account.teams.find_by(id: gid)
    end
  end

  def group_id(team)
    return if team.nil?

    @group_ids ||= ZendeskCompat::Config.groups.each_with_object({}) do |(zid, group), memo|
      memo[(group['team_name'] || group['name']).to_s.downcase] ||= zid.to_i
    end
    @group_ids[team.name.to_s.downcase] || team.id
  end

  def company(organization_id)
    oid = ZendeskCompat::Ids.integer(organization_id)
    return if oid.nil?

    if oid >= ZendeskCompat::Ids::ORG_BASE
      account.companies.find_by(id: oid - ZendeskCompat::Ids::ORG_BASE)
    else
      account.companies.where("custom_attributes->>'zd_org_id' = ?", oid.to_s).first
    end
  end

  private

  def find_actor(zid)
    ids = ZendeskCompat::Ids
    return account_user_scope.find_by(id: zid - ids::USER_BASE) if zid.between?(ids::USER_BASE, ids::BOT_BASE - 1)
    return account_bots.find_by(id: zid - ids::BOT_BASE) if zid.between?(ids::BOT_BASE, ids::ORG_BASE - 1)

    origin_actor(zid) || account.contacts.find_by(id: zid)
  end

  def origin_actor(zid)
    account_user_scope.where("users.custom_attributes->>'zendesk_user_id' = ?", zid.to_s).first ||
      account_bots.where("bot_config->>'zendesk_user_id' = ?", zid.to_s).first ||
      account.contacts.find_by(identifier: "zd:#{zid}") ||
      account.contacts.where("custom_attributes->>'zd_user_id' = ?", zid.to_s).first
  end

  # Agentes da conta e também usuários sem acesso que são autores do histórico (decisão 4 da importação).
  def account_user_scope
    member_ids = account.account_users.select(:user_id)
    author_ids = Message.where(account_id: account.id, sender_type: 'User').select(:sender_id)
    User.where(id: member_ids).or(User.where(id: author_ids))
  end

  def account_bots
    AgentBot.where(account_id: [account.id, nil])
  end
end
