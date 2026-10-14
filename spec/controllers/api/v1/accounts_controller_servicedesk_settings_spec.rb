require 'rails_helper'

RSpec.describe 'Accounts API: ServiceDesk settings (M1)', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }

  it 'exposes the effective value (off by default) and lets an administrator change it' do
    get "/api/v1/accounts/#{account.id}", headers: admin.create_new_auth_token, as: :json
    expect(response.parsed_body['servicedesk']).to eq('require_form_on_resolve' => false)

    patch "/api/v1/accounts/#{account.id}",
          params: { servicedesk_require_form_on_resolve: 'true' },
          headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(account.reload.servicedesk_require_form_on_resolve?).to be(true)
    expect(response.parsed_body['servicedesk']).to eq('require_form_on_resolve' => true)
  end

  it 'falls back to the installation default' do
    with_modified_env SD_REQUIRE_FORM_ON_RESOLVE: 'true' do
      expect(account.servicedesk_require_form_on_resolve?).to be(true)
    end
    expect(account.servicedesk_require_form_on_resolve?).to be(false)
  end
end
