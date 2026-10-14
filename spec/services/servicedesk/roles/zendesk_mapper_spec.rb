# frozen_string_literal: true

require 'rails_helper'

# ServiceDesk M13: os papéis semeados são exatamente as permissões do custom_roles.json do Zendesk da B2B.
RSpec.describe Servicedesk::Roles::ZendeskMapper do
  let(:roles) { JSON.parse(Rails.root.join('spec/fixtures/servicedesk/zendesk_custom_roles.json').read) }
  let(:by_id) { Servicedesk::Roles::Defaults::ROLES.values.index_by { |attrs| attrs[:zendesk_custom_role_id] } }

  it 'cada papel personalizado do Zendesk vira exatamente o papel padrão do ServiceDesk' do
    expect(roles.size).to eq(4)
    roles.each do |role|
      expected = by_id.fetch(role['id'])
      expect(described_class.permissions(role['configuration'])).to eq(expected[:permissions].to_h), role['name']
    end
  end

  it 'traduz os níveis do Zendesk' do
    light = roles.find { |r| r['name'] == 'Agente light' }['configuration']
    colaborador = roles.find { |r| r['name'] == 'Colaborador' }['configuration']
    expect(described_class.permissions(light)).to include('ticket.access' => 'all', 'ticket.comment_public' => false,
                                                          'views' => 'readonly', 'reports' => 'readonly', 'contacts.views' => 'none')
    expect(described_class.permissions(colaborador)).to include('ticket.access' => 'groups', 'contacts.list' => 'none',
                                                                'reports' => 'none', 'team_directory' => 'none')
    expect(described_class.permissions(light.merge('ticket_access' => 'assigned-only'))['ticket.access']).to eq('assigned')
  end
end
