require 'rails_helper'

RSpec.describe 'Conversations API: required form on resolve (ServiceDesk)', type: :request do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:inbox) { create(:inbox, account: account) }
  let(:conversation) { create(:conversation, account: account, inbox: inbox, status: :open) }

  before do
    account.update!(servicedesk_require_form_on_resolve: true)
    create(:inbox_member, inbox: inbox, user: agent)
    create(:custom_attribute_definition, account: account, attribute_model: :conversation_attribute,
                                         attribute_key: 'zd_area_interna', attribute_display_name: 'Área interna',
                                         attribute_display_type: :list, attribute_values: %w[Suporte],
                                         attribute_description: 'zendesk_field:21587135564955')
  end

  def toggle(params = { status: 'resolved' })
    post "/api/v1/accounts/#{account.id}/conversations/#{conversation.display_id}/toggle_status",
         params: params, headers: agent.create_new_auth_token, as: :json
  end

  it 'blocks resolving while a required form field is empty' do
    toggle
    expect(response).to have_http_status(:unprocessable_entity)
    expect(response.parsed_body['missing_attributes']).to eq([{ 'key' => 'zd_area_interna', 'name' => 'Área interna' }])
    expect(conversation.reload.status).to eq('open')
  end

  it 'blocks the plain toggle from open too' do
    toggle({})
    expect(response).to have_http_status(:unprocessable_entity)
  end

  it 'resolves when the field is filled' do
    conversation.update!(custom_attributes: { 'zd_area_interna' => 'Suporte' })
    toggle
    expect(response).to have_http_status(:success)
    expect(conversation.reload.status).to eq('resolved')
  end

  it 'does not block other status changes' do
    toggle({ status: 'on_hold' })
    expect(response).to have_http_status(:success)
  end

  it 'blocks "Submit as Solved" (reply + status) without creating the message' do
    post "/api/v1/accounts/#{account.id}/conversations/#{conversation.display_id}/messages",
         params: { content: 'Resolvido', ticket_status: 'resolved' }, headers: agent.create_new_auth_token, as: :json
    expect(response).to have_http_status(:unprocessable_entity)
    expect(conversation.reload.status).to eq('open')
    expect(conversation.messages.where(content: 'Resolvido')).to be_empty
  end

  it 'lets "Submit as Pending" through' do
    post "/api/v1/accounts/#{account.id}/conversations/#{conversation.display_id}/messages",
         params: { content: 'Aguardando', ticket_status: 'waiting_on_customer' }, headers: agent.create_new_auth_token, as: :json
    expect(response).to have_http_status(:success)
    expect(conversation.reload.status).to eq('waiting_on_customer')
  end

  it 'is off by default (SD_REQUIRE_FORM_ON_RESOLVE unset)' do
    account.update!(servicedesk_require_form_on_resolve: nil)
    toggle
    expect(response).to have_http_status(:success)
  end

  it 'can be turned off for the account' do
    account.update!(servicedesk_require_form_on_resolve: false)
    toggle
    expect(response).to have_http_status(:success)
    expect(conversation.reload.status).to eq('resolved')
  end
end
