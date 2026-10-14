require 'rails_helper'

RSpec.describe 'Ticket CCs API', type: :request do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:conversation) { create(:conversation, account: account) }
  let(:url) { "/api/v1/accounts/#{account.id}/conversations/#{conversation.display_id}/ccs" }

  before { create(:inbox_member, inbox: conversation.inbox, user: agent) }

  it 'adds, lists and removes CCs' do
    post url, params: { email: 'gerente@example.com' }, headers: agent.create_new_auth_token, as: :json
    expect(response.parsed_body['payload']).to eq(['gerente@example.com'])

    get url, headers: agent.create_new_auth_token, as: :json
    expect(response.parsed_body['payload']).to eq(['gerente@example.com'])

    delete url, params: { email: 'gerente@example.com' }, headers: agent.create_new_auth_token, as: :json
    expect(response.parsed_body['payload']).to eq([])
  end

  it 'rejects an invalid e-mail' do
    post url, params: { email: 'not-an-email' }, headers: agent.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unprocessable_entity)
  end
end
