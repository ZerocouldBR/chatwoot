class TicketRulesListener < BaseListener
  def account_created(event)
    Tickets::Rules::Defaults.new(event.data[:account]).seed
  end
end
