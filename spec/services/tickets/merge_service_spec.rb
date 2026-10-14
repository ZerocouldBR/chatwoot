require 'rails_helper'

RSpec.describe Tickets::MergeService do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :administrator) }
  let(:inbox) { create(:inbox, account: account) }
  let(:source) { create(:conversation, account: account, inbox: inbox, status: :open, subject: 'Origem') }
  let(:target) { create(:conversation, account: account, inbox: inbox, status: :open, subject: 'Destino') }

  before { source.contact.update!(email: 'origem@example.com') }

  it 'closes the source with the merge tag, comments on both and copies the source requester' do
    described_class.new(source: source, target: target, user: agent).perform

    expect(source.reload).to have_attributes(status: 'closed', merged_into_id: target.id)
    expect(source.label_list).to include('closed_by_merge')
    expect(source.messages.last).to have_attributes(private: true)
    expect(source.messages.last.content).to include("##{target.display_id}")
    expect(target.messages.last.content).to include("##{source.display_id}")
    expect(target.conversation_ccs.pluck(:email)).to eq(['origem@example.com'])
  end

  it 'uses the agent comments and can make them public' do
    described_class.new(source: source, target: target, user: agent, target_comment: 'Juntei aqui', public: true).perform

    expect(target.messages.last).to have_attributes(content: 'Juntei aqui', private: false)
  end

  it 'refuses solved sources and closed targets' do
    source.update!(status: :resolved)
    expect { described_class.new(source: source, target: target, user: agent).perform }
      .to raise_error(CustomExceptions::Ticket::MergeNotAllowed)

    expect { described_class.new(source: target, target: target, user: agent).perform }
      .to raise_error(CustomExceptions::Ticket::MergeNotAllowed)
  end
end
