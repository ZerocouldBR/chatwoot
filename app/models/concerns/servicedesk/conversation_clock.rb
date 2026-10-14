# Relógios do ticket no payload da lista (colunas Resolvido e Solicitante/Atribuído atualizado das views).
# Só as listas (index e filter) preenchem `sd_clock`, de uma vez (Servicedesk::TicketClocks.preload); nos demais
# payloads o campo não vai, para nunca virar N+1. `sd_clock!` calcula na hora para um ticket avulso.
module Servicedesk::ConversationClock
  extend ActiveSupport::Concern

  include Servicedesk::ConversationViewSorts

  attr_accessor :sd_clock

  def sd_clock!
    @sd_clock ||= Servicedesk::TicketClocks.for(self)
  end
end
