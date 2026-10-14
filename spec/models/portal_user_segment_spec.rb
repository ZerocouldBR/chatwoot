require 'rails_helper'

RSpec.describe PortalUserSegment do
  let(:account) { create(:account) }
  let(:portal) { create(:portal, account: account) }
  let(:contact) { create(:contact, account: account) }

  def segment(attrs = {})
    described_class.create!({ account: account, portal: portal, name: 'Segmento' }.merge(attrs))
  end

  it 'usuários conectados: qualquer contato da conta, nunca anônimo nem de outra conta' do
    seg = segment
    expect(seg.matches?(contact)).to be(true)
    expect(seg.matches?(nil)).to be(false)
    expect(seg.matches?(create(:contact, account: create(:account)))).to be(false)
  end

  it 'equipe (staff) nunca aparece para contato' do
    expect(segment(user_type: :staff).matches?(contact)).to be(false)
  end

  it 'organização: só contatos da empresa do segmento' do
    seg = segment(company_ids: [101])
    contact.company_id = 101
    expect(seg.matches?(contact)).to be(true)
    contact.company_id = 202
    expect(seg.matches?(contact)).to be(false)
  end

  it 'tags: todas obrigatórias; or_tags: pelo menos uma (sem diferenciar maiúsculas)' do
    contact.update!(label_list: %w[vip hotel])
    expect(segment(tags: %w[VIP hotel]).matches?(contact)).to be(true)
    expect(segment(tags: %w[vip agencia]).matches?(contact)).to be(false)
    expect(segment(or_tags: %w[agencia hotel]).matches?(contact)).to be(true)
    expect(segment(or_tags: %w[agencia ota]).matches?(contact)).to be(false)
  end

  it 'contatos avulsos (added_user_ids) entram mesmo fora da organização' do
    seg = segment(company_ids: [101], contact_ids: [contact.id])
    expect(seg.matches?(contact)).to be(true)
  end

  it 'visible_ids_for devolve só os segmentos do portal que o contato atende' do
    open_seg = segment
    segment(user_type: :staff)
    segment(company_ids: [999])
    other_portal_seg = described_class.create!(account: account, portal: create(:portal, account: account), name: 'Outro')
    expect(described_class.visible_ids_for(portal, contact)).to eq([open_seg.id])
    expect(described_class.visible_ids_for(portal, nil)).to eq([])
    expect(described_class.visible_ids_for(portal, contact)).not_to include(other_portal_seg.id)
  end

  it 'recusa portal de outra conta' do
    expect { described_class.create!(account: create(:account), portal: portal, name: 'x') }.to raise_error(ActiveRecord::RecordInvalid)
  end

  it 'Article.visible_to_segments mantém os públicos e só os segmentos liberados' do
    agent = create(:user, account: account)
    seg = segment
    other = segment(name: 'Outro')
    public_article = create(:article, portal: portal, account: account, author: agent)
    restricted = create(:article, portal: portal, account: account, author: agent, portal_user_segment: seg)
    hidden = create(:article, portal: portal, account: account, author: agent, portal_user_segment: other)
    expect(Article.visible_to_segments([])).to include(public_article)
    expect(Article.visible_to_segments([])).not_to include(restricted, hidden)
    expect(Article.visible_to_segments([seg.id])).to include(public_article, restricted)
    expect(Article.visible_to_segments([seg.id])).not_to include(hidden)
  end
end
