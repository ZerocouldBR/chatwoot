require 'rails_helper'

RSpec.describe 'SLA report API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:url) { "/api/v1/accounts/#{account.id}/applied_slas" }
  let(:policy) { SlaPolicy.create!(account: account, name: 'Urgentes', position: 1) }
  let!(:missed) do
    conversation = create(:conversation, account: account)
    applied = AppliedSla.create!(account: account, sla_policy: policy, conversation: conversation, sla_status: :missed)
    SlaEvent.create!(account: account, applied_sla: applied, conversation: conversation, sla_policy: policy, inbox: conversation.inbox,
                     event_type: :breach, meta: { metric: 'first_reply_time' })
    applied
  end

  before { AppliedSla.create!(account: account, sla_policy: policy, conversation: create(:conversation, account: account), sla_status: :hit) }

  it 'lists applied SLAs with their breaches' do
    get url, headers: admin.create_new_auth_token, as: :json

    row = response.parsed_body['payload'].find { |item| item['applied_sla']['id'] == missed.id }
    expect(response.parsed_body['meta']['count']).to eq(2)
    expect(row['applied_sla']).to include('sla_name' => 'Urgentes', 'sla_status' => 'missed')
    expect(row['sla_events'].pluck('metric')).to eq(['first_reply_time'])
  end

  it 'returns the hit rate' do
    get "#{url}/metrics", headers: admin.create_new_auth_token, as: :json

    expect(response.parsed_body).to eq('total_applied_slas' => 2, 'number_of_sla_misses' => 1, 'hit_rate' => '50.0%')
  end

  it 'filters by group' do
    team = create(:team, account: account)
    missed.conversation.update!(team: team)

    get "#{url}/metrics", params: { team_id: team.id }, headers: admin.create_new_auth_token

    expect(response.parsed_body['total_applied_slas']).to eq(1)
  end

  it 'is not available to agents' do
    get url, headers: agent.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unauthorized)
  end
end
