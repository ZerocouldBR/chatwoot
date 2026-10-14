require 'rails_helper'

# Camada que isola o modelo de ticket (legado x nativo do feat/tickets-f10). Aqui o modelo nativo é forçado só para as
# traduções que não dependem das colunas novas; o modelo nativo completo é coberto por native_ticket_model_spec.rb numa base f10.
RSpec.describe ZendeskCompat::TicketModel do
  after { described_class.force!(nil) }

  it 'detecta o modelo pelo schema' do
    described_class.force!(nil)
    expect(described_class.native?).to eq(Conversation.statuses.key?('new_ticket'))
  end

  context 'when native (enum de status do Zendesk)' do
    before { described_class.force!(true) }

    let(:ticket) { Struct.new(:status, :custom_attributes) }
    let(:translator) { ZendeskCompat::StatusTranslator }

    it 'lê a categoria direto do enum' do
      expect(translator.category(ticket.new('new_ticket', {}))).to eq('new')
      expect(translator.category(ticket.new('waiting_on_customer', {}))).to eq('pending')
      expect(translator.category(ticket.new('on_hold', {}))).to eq('hold')
      expect(translator.category(ticket.new('resolved', {}))).to eq('solved')
      expect(translator.category(ticket.new('closed', {}))).to eq('closed')
    end

    it 'grava o status do Zendesk no enum' do
      expect(translator.attributes_for(status: 'new')).to include(native: 'new_ticket', system_label: nil)
      expect(translator.attributes_for(status: 'pending')).to include(native: 'waiting_on_customer')
      expect(translator.attributes_for(status: 'hold')).to include(native: 'on_hold')
      expect(translator.attributes_for(status: 'closed')).to include(native: 'closed', system_label: nil)
      expect(translator.attributes_for(status: 'bogus')).to be_nil
    end

    it 'refina custom_status_id pelo rótulo zd_status quando o fork tem os status personalizados' do
      skip 'fork sem config/servicedesk/ticket_statuses.yml' unless described_class.labels?

      expect(translator.custom_status_id(ticket.new('on_hold', { 'zd_status' => 'Devolvido' }))).to eq(26_904_974_432_923)
      expect(translator.custom_status_id(ticket.new('on_hold', { 'zd_status' => 'Pendente' }))).to eq(21_790_243_451_291)
      expect(translator.custom_status_id(ticket.new('closed', {}))).to eq(20_487_384_870_939)
      expect(translator.attributes_for(status: 'pending')).to include(label: 'Pendente')
      expect(translator.attributes_for(custom_status_id: 23_819_380_599_963)).to include(native: 'resolved', label: 'Respondido cliente')
    end
  end
end
