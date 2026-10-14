require 'rails_helper'

RSpec.describe 'Agent home API', type: :request do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :administrator) }

  before { create(:conversation, account: account, assignee: agent, status: :open) }

  it 'returns the requested view with the counts of all views' do
    get "/api/v1/accounts/#{account.id}/ticket_home", params: { view: 'mine' }, headers: agent.create_new_auth_token, as: :json

    expect(response).to have_http_status(:success)
    expect(response.parsed_body['payload'].size).to eq(1)
    expect(response.parsed_body['meta']['counts']).to include('mine' => 1, 'ccs' => 0)
  end

  it 'rejects an unknown view' do
    get "/api/v1/accounts/#{account.id}/ticket_home", params: { view: 'everything' }, headers: agent.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unprocessable_entity)
  end

  it 'returns the home stats' do
    create(:csat_survey_response, account: account, assigned_agent: agent, rating: 5)
    create(:csat_survey_response, account: account, assigned_agent: agent, rating: 1)

    get "/api/v1/accounts/#{account.id}/ticket_home/stats", headers: agent.create_new_auth_token, as: :json

    expect(response.parsed_body).to include('week' => include('good' => 1, 'bad' => 1), 'satisfaction' => { 'you' => 50, 'support' => 50 })
  end
end
