require 'rails_helper'

RSpec.describe 'Ticket rules API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:url) { "/api/v1/accounts/#{account.id}/ticket_rules" }
  let(:params) do
    { kind: 'trigger',
      ticket_rule: { title: 'VIP', conditions: { all: [{ field: 'labels', operator: 'includes', value: 'vip' }], any: [] },
                     actions: [{ field: 'priority', value: 'urgent' },
                               { field: 'email_group', value: { team_id: '', subject: 'VIP #{{ticket.id}}', body: 'Veja' } }] } }
  end

  it 'creates triggers at the end of the order and reorders them' do
    post url, params: params, headers: admin.create_new_auth_token, as: :json
    post url, params: params.deep_merge(ticket_rule: { title: 'Outro' }), headers: admin.create_new_auth_token, as: :json
    first, second = TicketRule.ordered.to_a

    expect(first.actions.last).to eq('field' => 'email_group', 'value' => { 'team_id' => '', 'subject' => 'VIP #{{ticket.id}}', 'body' => 'Veja' })
    post "#{url}/reorder", params: { kind: 'trigger', ids: [second.id, first.id] }, headers: admin.create_new_auth_token, as: :json
    expect(response.parsed_body['payload'].pluck('title')).to eq(%w[Outro VIP])
  end

  it 'lists rules of one kind' do
    post url, params: params, headers: admin.create_new_auth_token, as: :json

    get url, params: { kind: 'automation' }, headers: admin.create_new_auth_token

    expect(response.parsed_body['payload']).to be_empty
  end

  it 'rejects an unknown kind' do
    get url, params: { kind: 'macro' }, headers: admin.create_new_auth_token

    expect(response).to have_http_status(:unprocessable_entity)
  end

  it 'rejects invalid conditions' do
    params[:ticket_rule][:conditions][:all] = [{ field: 'hours_since_created', operator: 'greater_than', value: '2' }]

    post url, params: params, headers: admin.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unprocessable_entity)
  end

  it 'is only for administrators' do
    get url, params: { kind: 'trigger' }, headers: agent.create_new_auth_token

    expect(response).to have_http_status(:unauthorized)
  end
end
