require 'rails_helper'

RSpec.describe 'ServiceDesk views API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }

  before do
    create(:custom_filter, account: account, user: admin, filter_type: :conversation, name: 'Novos',
                           query: { 'payload' => [], 'zendesk' => { 'view_id' => '1', 'posicao' => 28, 'visibilidade' => {} } })
  end

  it 'requires authentication' do
    get "/api/v1/accounts/#{account.id}/servicedesk/views"
    expect(response).to have_http_status(:unauthorized)
  end

  it 'lists the views visible to the agent' do
    get "/api/v1/accounts/#{account.id}/servicedesk/views", headers: agent.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    view = response.parsed_body['payload'].first
    expect(view).to include('name' => 'Novos', 'position' => 28, 'shared' => true)
    expect(view['query']).to eq('payload' => [])
  end

  it 'returns the counts by view id' do
    create(:conversation, account: account)
    get "/api/v1/accounts/#{account.id}/servicedesk/views/counts", headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(response.parsed_body['payload'].values).to eq([1])
  end
end
