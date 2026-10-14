# ServiceDesk B2B: status do ticket como o usuário final vê no Zendesk ("Minhas solicitações").
#
# O Zendesk mostra ao cliente o "rótulo do usuário final" de cada status personalizado
# (custom_statuses.json → end_user_label) e agrupa em três filtros: Aberto, Aguardando sua resposta e
# Resolvido. A categoria vem do status nativo do ticket (enum do Conversation, igual ao Zendesk):
#   new_ticket, open, pending (bot) e on_hold => Aberto (o cliente não vê "Em espera", como no Zendesk)
#   waiting_on_customer                       => Aguardando sua resposta
#   resolved e closed                         => Resolvido
# O rótulo personalizado vem de `zd_status` só quando ele é coerente com o status nativo; se o agente mudou
# o status direto no painel, vale o rótulo padrão da categoria.
class PortalCustomers::RequestStatus
  # zd_status (rótulo do agente) => [categoria Zendesk, rótulo do usuário final]
  ZENDESK_STATUSES = {
    'Novo' => %w[new Aberto],
    'Aberto' => %w[open Aberto],
    'Em andamento' => ['open', 'Em andamento'],
    'Devolvido Cliente' => ['open', 'Devolvido Cliente'],
    'Reaberto' => %w[open Reaberto],
    'Pendente' => ['pending', 'Aguardando resposta'],
    'Pendente Autenticação' => ['pending', 'Pendente Autenticação'],
    'Aguardando Desenvolvimento' => %w[hold Aberto],
    'Escalonado' => %w[hold Escalonado],
    'Desenvolvimento' => %w[hold Desenvolvimento],
    'Retorno Integrações' => ['hold', 'Retorno Integrações'],
    'Devolvido' => %w[hold Devolvido],
    'Desenvolvimento Concluído' => ['hold', 'Desenvolvimento Concluído'],
    'Resolvido' => %w[solved Resolvido],
    'Concluído' => %w[solved Concluído],
    'Respondido cliente' => ['solved', 'Respondido cliente'],
    'Autenticação Pendente' => ['solved', 'Autenticação Pendente'],
    'Fechado' => %w[closed Resolvido]
  }.freeze

  # status nativo => categorias do Zendesk compatíveis com ele (para aceitar o rótulo do zd_status)
  NATIVE_CATEGORIES = {
    'new_ticket' => %w[new open], 'open' => %w[new open], 'pending' => %w[new open], 'on_hold' => %w[hold],
    'waiting_on_customer' => %w[pending], 'resolved' => %w[solved], 'closed' => %w[solved closed]
  }.freeze

  # status nativo => filtro do portal
  STATUS_GROUPS = {
    'new_ticket' => 'open', 'open' => 'open', 'pending' => 'open', 'on_hold' => 'open',
    'waiting_on_customer' => 'awaiting', 'resolved' => 'solved', 'closed' => 'solved'
  }.freeze
  GROUPS = %w[open awaiting solved].freeze

  attr_reader :conversation

  def initialize(conversation)
    @conversation = conversation
  end

  # open | awaiting | solved (filtros do Zendesk: Aberto, Aguardando sua resposta, Resolvido)
  def group
    STATUS_GROUPS.fetch(conversation.status.to_s, 'open')
  end

  def label
    entry = coherent_zendesk_entry
    return entry.last if entry

    I18n.t("public_portal.sd.requests.status.#{group}")
  end

  # Fechado (status nativo closed): o cliente não comenta mais no ticket; a resposta vira um acompanhamento.
  def closed?
    conversation.closed?
  end

  # Filtro da lista no banco, com a mesma regra de #group.
  def self.filter(relation, group)
    return relation unless GROUPS.include?(group)

    relation.where(status: STATUS_GROUPS.select { |_status, value| value == group }.keys)
  end

  private

  def coherent_zendesk_entry
    entry = ZENDESK_STATUSES[custom_attribute('zd_status').to_s.strip]
    return unless entry
    return unless NATIVE_CATEGORIES.fetch(conversation.status.to_s, []).include?(entry.first)

    entry
  end

  def custom_attribute(key)
    (conversation.custom_attributes || {})[key]
  end
end
