require 'rails_helper'

RSpec.describe 'Accounts API: ServiceDesk settings', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }

  describe 'PATCH /api/v1/accounts/{account.id}' do
    it 'lets an administrator turn macro_fill_editor off and on' do
      patch "/api/v1/accounts/#{account.id}", params: { macro_fill_editor: false }, headers: admin.create_new_auth_token, as: :json

      expect(response).to have_http_status(:success)
      expect(account.reload.macro_fill_editor?).to be(false)
      expect(response.parsed_body['settings']['macro_fill_editor']).to be(false)

      patch "/api/v1/accounts/#{account.id}", params: { macro_fill_editor: true }, headers: admin.create_new_auth_token, as: :json

      expect(account.reload.macro_fill_editor?).to be(true)
    end

    it 'does not let an agent change it' do
      patch "/api/v1/accounts/#{account.id}", params: { macro_fill_editor: false }, headers: agent.create_new_auth_token, as: :json

      expect(response).to have_http_status(:unauthorized)
      expect(account.reload.settings['macro_fill_editor']).to be_nil
    end
  end
end
