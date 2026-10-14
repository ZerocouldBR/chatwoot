# Visualizações (views) do Agent Workspace para quem está logado.
#
# Fonte: filtros salvos (`custom_filters`) com a chave `query.zendesk`, gravados pelo import_rules_views
# (posição, colunas, ordenação, agrupamento e a restrição da view). Esses filtros pertencem ao dono da
# importação, mas valem para a conta inteira, com a visibilidade do Zendesk (`query.zendesk.visibilidade`):
#   - sem restrição (tipo vazio): todos os agentes;
#   - tipo Group: membros de um dos grupos da view. O grupo do agente vem só dos times dele (`team_members`; o
#     time é ligado ao grupo pela descrição `zendesk_group:<id>` ou pelos `team_ids` gravados na importação). É a
#     mesma fonte do M13 (Servicedesk::Roles::TicketScope e servicedesk_role.team_ids), para que a view e os
#     tickets que ela lista sigam os mesmos grupos. `users.custom_attributes.zendesk_groups` não conta;
#   - tipo User: só o usuário dono da view (`users.custom_attributes.zendesk_user_id`);
#   - administrador vê todas; as que não são dos grupos dele vêm com `member: false` (o painel as separa).
# Os filtros pessoais de quem está logado (sem `query.zendesk`) entram como "pessoais", depois das compartilhadas.
class Servicedesk::SharedViews
  COUNT_TTL = 60.seconds
  GROUP_PREFIX = 'zendesk_group:'.freeze

  pattr_initialize [:account!, :user!]

  def views
    shared_views + personal_views
  end

  # { custom_filter_id => quantidade } das views visíveis; nil quando o filtro não pôde ser executado.
  def counts
    views.to_h { |view| [view[:id], count_for(view)] }
  end

  # A view é de um grupo (ou usuário) de quem está logado? Administradores enxergam as demais também.
  def member?(meta)
    visibility = meta['visibilidade'] || {}
    case visibility['tipo'].presence
    when nil then true
    when 'User' then Array(visibility['zd_user_ids'] || visibility['zd_group_ids']).map(&:to_s).include?(user_zd_id)
    else group_member?(visibility)
    end
  end

  private

  def administrator?
    @administrator ||= account.account_users.find_by(user_id: user.id)&.administrator? || false
  end

  def user_teams
    @user_teams ||= user.teams.where(account_id: account.id).to_a
  end

  # Grupos do Zendesk de quem está logado: pelos times dele (descrição zendesk_group:<id>), a mesma fonte do M13
  def user_zd_group_ids
    @user_zd_group_ids ||= user_teams.filter_map { |team| zd_group_id(team) }.map(&:to_s).to_set
  end

  def user_zd_id
    (user.custom_attributes || {})['zendesk_user_id'].to_s.presence
  end

  def zd_group_id(team)
    description = team.description.to_s.strip
    description.delete_prefix(GROUP_PREFIX).strip.presence if description.start_with?(GROUP_PREFIX)
  end

  def group_member?(visibility)
    team_ids = Array(visibility['team_ids']).map(&:to_i)
    return true if team_ids.intersect?(user_teams.map(&:id))

    Array(visibility['zd_group_ids']).map(&:to_s).any? { |id| user_zd_group_ids.include?(id) }
  end

  def conversation_filters
    account.custom_filters.where(filter_type: :conversation)
  end

  def shared_views
    views = unique_shared_filters.filter_map do |filter|
      meta = filter.query['zendesk'] || {}
      member = member?(meta)
      serialize(filter, meta, shared: true, member: member) if member || administrator?
    end
    views.sort_by { |view| [view[:position] || Float::INFINITY, view[:name].to_s] }
  end

  # Uma view importada duas vezes (mesmo view_id) aparece uma vez só, a mais antiga
  def unique_shared_filters
    conversation_filters.where("query ? 'zendesk'").order(:id).uniq do |filter|
      filter.query.dig('zendesk', 'view_id').presence || "cf:#{filter.id}"
    end
  end

  def personal_views
    conversation_filters.where(user_id: user.id).where.not("query ? 'zendesk'").order(:name).map do |filter|
      serialize(filter, {}, shared: false, member: true)
    end
  end

  def serialize(filter, meta, shared:, member:)
    {
      id: filter.id,
      name: filter.name,
      shared: shared,
      member: member,
      owned: filter.user_id == user.id,
      position: meta['posicao'],
      description: meta['descricao'],
      columns: Array(meta['colunas']),
      sort: meta['ordenacao'] || {},
      group_by: meta['agrupamento'] || {},
      conversion: meta['conversao'],
      updated_at: filter.updated_at.to_i,
      query: { 'payload' => Array(filter.query['payload']) }
    }
  end

  # Administradores enxergam a conta toda (mesma contagem para todos). Para agentes a contagem depende das
  # inboxes e do acesso a tickets do papel (M13), então o cache é por usuário.
  def scope_key
    @scope_key ||= administrator? ? 'admin' : "user:#{user.id}"
  end

  def count_for(view)
    Rails.cache.fetch(['sd_view_count', account.id, view[:id], view[:updated_at], scope_key], expires_in: COUNT_TTL) do
      Servicedesk::ViewCountService.new({ payload: view[:query]['payload'] }.with_indifferent_access, user, account).count
    end
  rescue StandardError => e
    Rails.logger.warn("[servicedesk_view_count] view=#{view[:id]} #{e.class}: #{e.message}")
    nil
  end
end
