require 'rails_helper'

RSpec.describe 'Business schedules API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:url) { "/api/v1/accounts/#{account.id}/business_schedules" }
  let(:params) do
    { business_schedule: { name: 'Comercial', time_zone: 'America/Sao_Paulo', is_default: true,
                           intervals: [{ day: 1, start: 540, end: 1080 }],
                           holidays: [{ name: 'Natal', start_date: '2026-12-25', end_date: '2026-12-25' }] } }
  end

  it 'lets admins create and update schedules' do
    post url, params: params, headers: admin.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    schedule = BusinessSchedule.default_for(account)
    expect(schedule.intervals).to eq([{ 'day' => 1, 'start' => 540, 'end' => 1080 }])

    patch "#{url}/#{schedule.id}", params: { business_schedule: { name: 'Suporte' } }, headers: admin.create_new_auth_token, as: :json
    expect(schedule.reload.name).to eq('Suporte')
  end

  it 'rejects invalid intervals' do
    params[:business_schedule][:intervals] = [{ day: 1, start: 545, end: 1080 }]

    post url, params: params, headers: admin.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unprocessable_entity)
  end

  it 'lets agents read but not change schedules' do
    get url, headers: agent.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)

    post url, params: params, headers: agent.create_new_auth_token, as: :json
    expect(response).to have_http_status(:unauthorized)
  end
end
