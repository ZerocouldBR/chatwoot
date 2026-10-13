require 'rails_helper'

RSpec.describe Servicedesk::TicketStatusFilter do
  let!(:account) { create(:account) }
  let!(:admin) { create(:user, account: account, role: :administrator) }
  let!(:inbox) { create(:inbox, account: account, enable_auto_assignment: false) }

  let!(:pending_labeled) { ticket(:snoozed, 'Pendente') }
  let!(:pending_unlabeled) { ticket(:snoozed) }
  let!(:hold_accented) { ticket(:snoozed, 'Desenvolvimento Concluído') }
  let!(:hold_plain) { ticket(:snoozed, 'desenvolvimento concluido') }
  let!(:hold_inactive) { ticket(:snoozed, 'Escalonado') }
  let!(:open_ticket) { ticket(:open, 'Em andamento') }
  let!(:resolved_ticket) { ticket(:resolved, 'Resolvido') }

  before { Current.account = account }

  def ticket(status, zd_status = nil)
    attrs = zd_status ? { 'zd_status' => zd_status } : {}
    create(:conversation, account: account, inbox: inbox, status: status, custom_attributes: attrs)
  end

  def finder_ids(params)
    ConversationFinder.new(admin, params).perform[:conversations].map(&:id)
  end

  describe 'via ConversationFinder' do
    it 'returns only snoozed tickets of the hold category for Em espera' do
      expect(finder_ids(status: 'snoozed', zd_status_category: 'hold'))
        .to contain_exactly(hold_accented.id, hold_plain.id, hold_inactive.id)
    end

    it 'returns the other snoozed tickets (labeled pending or without label) for Pendente' do
      expect(finder_ids(status: 'snoozed', zd_status_category: 'pending'))
        .to contain_exactly(pending_labeled.id, pending_unlabeled.id)
    end

    it 'keeps the native snoozed filter when no category is given' do
      expect(finder_ids(status: 'snoozed')).to contain_exactly(
        pending_labeled.id, pending_unlabeled.id, hold_accented.id, hold_plain.id, hold_inactive.id
      )
    end

    it 'ignores the category for other statuses' do
      expect(finder_ids(status: 'open', zd_status_category: 'hold')).to contain_exactly(open_ticket.id)
      expect(finder_ids(status: 'resolved', zd_status_category: 'pending')).to contain_exactly(resolved_ticket.id)
    end

    it 'ignores unknown categories' do
      expect(finder_ids(status: 'snoozed', zd_status_category: 'xyz').size).to eq(5)
    end

    it 'applies the category to the meta counts' do
      counts = ConversationFinder.new(admin, { status: 'snoozed', zd_status_category: 'hold' }).perform_meta_only[:count]
      expect(counts[:all_count]).to eq(3)
    end
  end

  describe 'HOLD_LABELS' do
    it 'matches the hold statuses of ticketFormsMeta.json (front-end source)' do
      meta_path = Rails.root.join('app/javascript/dashboard/servicedesk/ticketFormsMeta.json')
      meta = JSON.parse(File.read(meta_path))
      hold = meta.fetch('statuses').select { |_name, status| status['category'] == 'hold' }.keys
      expect(described_class::HOLD_LABELS).to match_array(hold)
    end
  end
end
