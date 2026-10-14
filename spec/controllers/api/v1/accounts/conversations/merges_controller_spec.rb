require 'rails_helper'

RSpec.describe 'Ticket merge and problem link API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:source) { create(:conversation, account: account, status: :open) }
  let(:target) { create(:conversation, account: account, status: :open) }
  let(:base) { "/api/v1/accounts/#{account.id}/conversations" }

  it 'merges a ticket into another and returns the target' do
    post "#{base}/#{source.display_id}/merge", params: { target_id: target.display_id }, headers: admin.create_new_auth_token, as: :json

    expect(response.parsed_body['id']).to eq(target.display_id)
    expect(source.reload).to have_attributes(status: 'closed', merged_into_id: target.id)
  end

  it 'explains why a merge is refused' do
    post "#{base}/#{source.display_id}/merge", params: { target_id: source.display_id }, headers: admin.create_new_auth_token, as: :json

    expect(response).to have_http_status(:unprocessable_entity)
    expect(response.parsed_body['message']).to be_present
  end

  it 'links an incident to a problem by ticket number' do
    problem = create(:conversation, account: account, ticket_type: :problem)
    source.update!(ticket_type: :incident)

    patch "#{base}/#{source.display_id}", params: { problem_id: problem.display_id }, headers: admin.create_new_auth_token, as: :json

    expect(source.reload.problem_id).to eq(problem.id)
    expect(response.parsed_body['problem_id']).to eq(problem.display_id)
  end
end
