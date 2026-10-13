require 'rails_helper'

RSpec.describe Servicedesk::TicketStatuses do
  describe '.native_status_for' do
    it 'derives the canonical native status from the category' do
      expect(described_class.native_status_for('Novo')).to eq('open')
      expect(described_class.native_status_for('Em andamento')).to eq('open')
      expect(described_class.native_status_for('Pendente')).to eq('snoozed')
      expect(described_class.native_status_for('Desenvolvimento')).to eq('snoozed')
      expect(described_class.native_status_for('Concluído')).to eq('resolved')
    end

    it 'never maps a status to the native pending (reserved to the bot queue)' do
      natives = described_class.labels.map { |label| described_class.native_status_for(label) }

      expect(natives.uniq).to match_array(%w[open snoozed resolved])
    end

    it 'returns nil for an unknown label' do
      expect(described_class.native_status_for('Inexistente')).to be_nil
    end
  end

  describe '.find' do
    it 'matches the exact label first and then ignores accents and case' do
      expect(described_class.find('Desenvolvimento Concluído')['category']).to eq('hold')
      expect(described_class.find('desenvolvimento concluido')['label']).to eq('Desenvolvimento Concluído')
    end
  end

  describe '.labels' do
    it 'lists the 11 active statuses' do
      expect(described_class.labels(active_only: true)).to eq(
        ['Novo', 'Aberto', 'Em andamento', 'Reaberto', 'Pendente', 'Desenvolvimento', 'Devolvido',
         'Desenvolvimento Concluído', 'Resolvido', 'Concluído', 'Respondido cliente']
      )
    end
  end

  it 'matches the status table used by the dashboard (ticketFormsMeta.json)' do
    meta = JSON.parse(Rails.root.join('app/javascript/dashboard/servicedesk/ticketFormsMeta.json').read)['statuses']
    from_yml = described_class.statuses.to_h do |status|
      [status['label'], { 'category' => status['category'], 'native' => described_class.native_status_for(status['label']),
                          'active' => status['active'], 'id' => status['origin_id'] }]
    end
    from_meta = meta.transform_values { |status| status.slice('category', 'native', 'active', 'id') }

    expect(from_yml).to eq(from_meta)
  end
end
