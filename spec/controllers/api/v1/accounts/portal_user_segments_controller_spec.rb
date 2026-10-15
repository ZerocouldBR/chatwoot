require 'rails_helper'

RSpec.describe 'Api::V1::Accounts::PortalUserSegments', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let!(:portal) { create(:portal, account: account, slug: 'central-b2b') }
  let!(:segment) { PortalUserSegment.create!(account: account, portal: portal, name: 'Usuários conectados') }
  let!(:article) { create(:article, portal: portal, account: account, author: admin) }

  it 'exige autenticação' do
    get "/api/v1/accounts/#{account.id}/portals/#{portal.slug}/user_segments"
    expect(response).to have_http_status(:unauthorized)
  end

  it 'lista os segmentos do portal' do
    get "/api/v1/accounts/#{account.id}/portals/#{portal.slug}/user_segments", headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(response.parsed_body['payload']).to contain_exactly(include('id' => segment.id, 'name' => 'Usuários conectados',
                                                                       'user_type' => 'signed_in'))
  end

  it 'o artigo grava e devolve o segmento e o token de pré-visualização' do
    patch "/api/v1/accounts/#{account.id}/portals/#{portal.slug}/articles/#{article.id}",
          params: { article: { portal_user_segment_id: segment.id } }, headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(article.reload.portal_user_segment_id).to eq(segment.id)
    expect(response.parsed_body['payload']['portal_user_segment_id']).to eq(segment.id)
    token = response.parsed_body['payload']['sd_preview_token']
    expect(Rails.application.message_verifier(:sd_article_preview).verified(token, purpose: :preview)).to eq(article.id)
  end

  it 'recusa segmento de outro portal' do
    other = PortalUserSegment.create!(account: account, portal: create(:portal, account: account), name: 'Outro')
    patch "/api/v1/accounts/#{account.id}/portals/#{portal.slug}/articles/#{article.id}",
          params: { article: { portal_user_segment_id: other.id } }, headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:unprocessable_entity)
    expect(article.reload.portal_user_segment_id).to be_nil
  end
end
