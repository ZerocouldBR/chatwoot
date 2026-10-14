require 'rails_helper'

RSpec.describe 'Trash and spam API', type: :request do
  let(:account) { create(:account) }
  let(:admin) { create(:user, account: account, role: :administrator) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:conversation) { create(:conversation, account: account) }
  let(:base) { "/api/v1/accounts/#{account.id}" }

  it 'moves deleted tickets to the trash, where they can be restored' do
    delete "#{base}/conversations/#{conversation.display_id}", headers: admin.create_new_auth_token

    expect(account.conversations.find_by(id: conversation.id)).to be_nil
    get "#{base}/deleted_tickets", headers: admin.create_new_auth_token
    expect(response.parsed_body['payload'].pluck('id')).to eq([conversation.display_id])

    post "#{base}/deleted_tickets/#{conversation.display_id}/restore", headers: admin.create_new_auth_token
    expect(account.conversations.find_by(id: conversation.id)).to be_present
  end

  it 'purges tickets trashed more than 30 days ago' do
    conversation.update!(deleted_at: 31.days.ago)
    recent = create(:conversation, account: account, deleted_at: 1.day.ago)

    perform_enqueued_jobs { Tickets::PurgeTrashJob.perform_now }

    expect(Conversation.unscoped.where(id: [conversation.id, recent.id]).pluck(:id)).to eq([recent.id])
  end

  it 'marks a ticket as spam: blocks the requester and trashes the ticket' do
    post "#{base}/conversations/#{conversation.display_id}/spam", headers: admin.create_new_auth_token

    expect(conversation.contact.reload).to be_blocked
    expect(Conversation.trashed.find_by(id: conversation.id)).to be_present
  end

  # ServiceDesk M13: o agente sem papel com ticket.view_deleted recebe o 403 da matriz de papéis
  it 'keeps the trash to administrators' do
    get "#{base}/deleted_tickets", headers: agent.create_new_auth_token

    expect(response).to have_http_status(:forbidden)
  end
end
