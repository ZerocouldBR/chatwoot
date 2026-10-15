# Origem das mudanças gravadas no histórico do ticket durante a requisição/job atual (ex.: 'api' na API de
# compatibilidade com o Zendesk). Sem valor, Servicedesk::TicketAuditTrail deduz pela execução (regra/painel).
module Servicedesk::TicketAuditContext
  thread_mattr_accessor :via

  def self.with(via)
    previous = self.via
    self.via = via
    yield
  ensure
    self.via = previous
  end
end
