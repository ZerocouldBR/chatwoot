require 'rails_helper'

RSpec.describe 'Outbound guard on the account API' do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }

  it 'tells the dashboard that the account is isolated' do
    account.update!(outbound_blocked: true)

    get "/api/v1/accounts/#{account.id}", headers: admin.create_new_auth_token, as: :json

    expect(response).to have_http_status(:success)
    expect(response.parsed_body.dig('servicedesk', 'outbound_blocked')).to be(true)
  end

  it 'reports SD_OUTBOUND_BLOCKED as isolated too' do
    with_modified_env SD_OUTBOUND_BLOCKED: 'true' do
      get "/api/v1/accounts/#{account.id}", headers: admin.create_new_auth_token, as: :json
    end

    expect(response.parsed_body.dig('servicedesk', 'outbound_blocked')).to be(true)
  end

  it 'cannot be turned off through the account settings API' do
    account.update!(outbound_blocked: true)

    patch "/api/v1/accounts/#{account.id}", params: { outbound_blocked: false }, headers: admin.create_new_auth_token, as: :json

    expect(account.reload.outbound_blocked).to be(true)
  end
end
