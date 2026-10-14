require 'rails_helper'

RSpec.describe Tickets::Rules::Defaults do
  let(:account) { create(:account, locale: 'pt_BR') }

  it 'creates the default triggers and automations once, in the account language' do
    described_class.new(account).seed
    described_class.new(account).seed

    expect(TicketRule.where(account: account).kind_trigger.ordered.first.title).to eq('Notificar solicitante e CCs sobre pedido recebido')
    expect(TicketRule.where(account: account).group(:kind).count).to eq('trigger' => 3, 'automation' => 2)
    expect(TicketRule.where(account: account).kind_automation.pluck(:active)).to all(be(false))
  end
end
