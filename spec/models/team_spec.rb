require 'rails_helper'

RSpec.describe Team do
  describe 'associations' do
    it { is_expected.to belong_to(:account) }
    it { is_expected.to have_many(:conversations) }
    it { is_expected.to have_many(:team_members) }
  end

  describe 'name normalization' do
    let(:account) { create(:account) }

    it 'keeps the name as typed (case and accents)' do
      team = create(:team, account: account, name: 'Alterações Cadastrais')
      expect(team.reload.name).to eq('Alterações Cadastrais')
    end

    it 'strips control characters and surrounding whitespace' do
      team = create(:team, account: account, name: "  Sales\n")
      expect(team.name).to eq('Sales')
    end

    it 'removes control characters embedded within the name' do
      team = create(:team, account: account, name: "Su\npport")
      expect(team.name).to eq('Support')
    end

    it 'keeps inner spacing as typed' do
      team = create(:team, account: account, name: 'Gestor  Comercial Empresas')
      expect(team.name).to eq('Gestor  Comercial Empresas')
    end

    it 'is invalid when the name reduces to blank after sanitization' do
      team = build(:team, account: account, name: "\t\n  ")
      expect(team).not_to be_valid
      expect(team.errors[:name]).to include(I18n.t('errors.validations.presence'))
    end
  end

  describe 'case-insensitive uniqueness' do
    let(:account) { create(:account) }
    let!(:team) { create(:team, account: account, name: 'Integrações - N3') }

    it 'rejects the same name with different case in the same account' do
      duplicate = build(:team, account: account, name: 'INTEGRAÇÕES - n3')
      expect(duplicate).not_to be_valid
      expect(duplicate.errors[:name]).to be_present
    end

    it 'allows the same name in another account' do
      expect(build(:team, name: 'Integrações - N3')).to be_valid
    end

    it 'allows renaming a team to another case of its own name' do
      team.update!(name: 'INTEGRAÇÕES - N3')
      expect(team.reload.name).to eq('INTEGRAÇÕES - N3')
    end

    it 'is enforced by the database index on lower(name)' do
      now = Time.current
      expect do
        # rubocop:disable Rails/SkipsModelValidations
        described_class.insert_all!([{ name: 'integrações - n3', account_id: account.id, created_at: now, updated_at: now }])
        # rubocop:enable Rails/SkipsModelValidations
      end.to raise_error(ActiveRecord::RecordNotUnique)
    end

    it 'is still found by the legacy lowercase name' do
      expect(account.teams.where('LOWER(name) = ?', 'integrações - n3')).to contain_exactly(team)
    end
  end

  describe '#add_members' do
    let(:team) { FactoryBot.create(:team) }

    before do
      allow(Rails.configuration.dispatcher).to receive(:dispatch)
    end

    it 'handles adds all members and resets cache keys' do
      users = FactoryBot.create_list(:user, 3)
      team.add_members(users.map(&:id))
      expect(team.reload.team_members.size).to eq(3)

      expect(Rails.configuration.dispatcher).to have_received(:dispatch).at_least(:once)
                                                                        .with(
                                                                          'account.cache_invalidated',
                                                                          kind_of(Time),
                                                                          account: team.account,
                                                                          cache_keys: team.account.cache_keys
                                                                        )
    end
  end

  describe '#remove_members' do
    let(:team) { FactoryBot.create(:team) }
    let(:users) { FactoryBot.create_list(:user, 3) }

    before do
      team.add_members(users.map(&:id))
      allow(Rails.configuration.dispatcher).to receive(:dispatch)
    end

    it 'removes the members and resets cache keys' do
      expect(team.reload.team_members.size).to eq(3)

      team.remove_members(users.map(&:id))
      expect(team.reload.team_members.size).to eq(0)

      expect(Rails.configuration.dispatcher).to have_received(:dispatch).at_least(:once)
                                                                        .with(
                                                                          'account.cache_invalidated',
                                                                          kind_of(Time),
                                                                          account: team.account,
                                                                          cache_keys: team.account.cache_keys
                                                                        )
    end
  end
end
