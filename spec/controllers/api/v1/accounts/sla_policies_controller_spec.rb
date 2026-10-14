require 'rails_helper'

RSpec.describe 'SLA policies API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:url) { "/api/v1/accounts/#{account.id}/sla_policies" }
  let(:params) do
    { sla_policy: { name: 'Urgentes',
                    filter: { all: [{ field: 'priority', operator: 'equal_to', values: ['urgent'] }] },
                    targets: [{ metric: 'first_reply_time', priority: 'urgent', minutes: 30, business_hours: false }] } }
  end

  it 'lets admins create policies appended at the end of the order' do
    post url, params: params, headers: admin.create_new_auth_token, as: :json
    post url, params: params.deep_merge(sla_policy: { name: 'Geral' }), headers: admin.create_new_auth_token, as: :json

    expect(SlaPolicy.where(account: account).ordered.pluck(:name, :position)).to eq([['Urgentes', 1], ['Geral', 2]])
    expect(SlaPolicy.find_by(name: 'Urgentes').targets.first).to include('metric' => 'first_reply_time', 'minutes' => 30)
  end

  it 'reorders policies' do
    first = SlaPolicy.create!(account: account, name: 'A', position: 1)
    second = SlaPolicy.create!(account: account, name: 'B', position: 2)

    post "#{url}/reorder", params: { ids: [second.id, first.id] }, headers: admin.create_new_auth_token, as: :json

    expect(response.parsed_body['payload'].pluck('name')).to eq(%w[B A])
  end

  it 'rejects invalid targets' do
    params[:sla_policy][:targets] = [{ metric: 'happiness', priority: 'urgent', minutes: 30, business_hours: false }]

    post url, params: params, headers: admin.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unprocessable_entity)
  end

  it 'does not let agents change policies' do
    post url, params: params, headers: agent.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unauthorized)
  end
end
