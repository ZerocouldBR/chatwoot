require 'rails_helper'

RSpec.describe 'Ticket events API', type: :request do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:conversation) { create(:conversation, account: account) }

  before { create(:inbox_member, inbox: conversation.inbox, user: agent) }

  it 'returns the audit trail newest first with readable names for id fields' do
    conversation.update!(assignee: agent)

    get "/api/v1/accounts/#{account.id}/conversations/#{conversation.display_id}/events",
        headers: agent.create_new_auth_token, as: :json

    expect(response).to have_http_status(:success)
    payload = response.parsed_body['payload']
    assignment = payload.find { |event| event['field_name'] == 'assignee_id' }
    expect(assignment).to include('value' => agent.id, 'value_label' => agent.name)
    expect(payload.last['event_type']).to eq('create')
  end

  it 'denies agents without access to the ticket' do
    outsider = create(:user, account: account, role: :agent)

    get "/api/v1/accounts/#{account.id}/conversations/#{conversation.display_id}/events",
        headers: outsider.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unauthorized)
  end
end
