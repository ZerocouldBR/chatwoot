require 'rails_helper'

RSpec.describe 'Zendesk compat: Sunshine Conversations (/sc/v2)', type: :request do
  include_context 'with zendesk compat data'

  let(:base) { '/b2b-reservas.zendesk.com/sc/v2/apps/6557c2ec7c66755a391c709b' }

  before do
    add_message(chat_ticket, type: :incoming, content: 'Oi, quero cancelar', sender: requester, created_at: 5.minutes.ago)
  end

  it 'acha a conversa do contato pelo userId do conversation_log (Recebe Mensagens Zendesk)' do
    user_id = ZendeskCompat::ConversationLogBuilder.sunco_user_id(requester)
    get "#{base}/conversations?#{{ filter: { userId: user_id } }.to_query}", headers: headers
    expect(json['conversations']).to contain_exactly(include('id' => chat_ticket.uuid, 'type' => 'personal'))
  end

  it 'lista as mensagens com o tipo do autor' do
    get "#{base}/conversations/#{chat_ticket.uuid}/messages", headers: headers
    expect(json['messages'].first).to include('author' => include('type' => 'user'),
                                              'content' => { 'type' => 'text',
                                                             'text' => 'Oi, quero cancelar' })
  end

  it 'envia texto como business (envia_msg / envia_aviso) e marca o autor no log' do
    body = { author: { type: 'business', displayName: 'Cema', avatarUrl: 'https://example.com/cema.png' }, content: { type: 'text', text: 'Ainda está aí?' } }
    post "#{base}/conversations/#{chat_ticket.uuid}/messages", params: body.to_json, headers: json_headers

    expect(response).to have_http_status(:created)
    message = chat_ticket.messages.last
    expect(message).to have_attributes(content: 'Ainda está aí?', message_type: 'outgoing', sender: cema, private: false)
    expect(json['messages'].first['author']).to include('type' => 'business', 'displayName' => 'Cema')

    get "/api/v2/tickets/#{chat_ticket.display_id}/conversation_log", headers: headers
    expect(json['events'].last['author']).to include('type' => 'business', 'display_name' => 'Cema')
  end

  it 'envia imagem enviada antes por /attachments (upload_sunshine + envia_msg)' do
    post "#{base}/attachments?access=public&for=message&conversationId=#{chat_ticket.uuid}",
         params: { source: fixture_file_upload(Rails.root.join('spec/assets/sample.png'), 'image/png') }, headers: headers
    expect(response).to have_http_status(:created)
    media_url = json.dig('attachment', 'mediaUrl')
    expect(json.dig('attachment', 'mediaType')).to eq('image/png')

    post "#{base}/conversations/#{chat_ticket.uuid}/messages",
         params: { author: { type: 'business', displayName: 'Cema' }, content: { type: 'image', mediaUrl: media_url } }.to_json, headers: json_headers
    expect(response).to have_http_status(:created)
    expect(chat_ticket.messages.last.attachments.first.file.blob.content_type).to eq('image/png')
    expect(json['messages'].first['content']).to include('type' => 'image')
  end

  it 'não baixa mediaUrl externa (400)' do
    post "#{base}/conversations/#{chat_ticket.uuid}/messages",
         params: { content: { type: 'image', mediaUrl: 'http://169.254.169.254/latest/meta-data' } }.to_json, headers: json_headers
    expect(response).to have_http_status(:bad_request)
    expect(json['errors'].first['code']).to eq('bad_request')
  end

  it 'aceita typing:start (sinaliza_digitando / realiza_delay)' do
    expect(Rails.configuration.dispatcher).to receive(:dispatch).with(Events::Types::CONVERSATION_TYPING_ON, anything, anything).and_call_original
    post "#{base}/conversations/#{chat_ticket.uuid}/activity", params: { author: { type: 'business' }, type: 'typing:start' }.to_json,
                                                               headers: json_headers
    expect(response).to have_http_status(:ok)
  end

  it 'responde 404 no formato do Sunshine para conversa inexistente' do
    get "#{base}/conversations/00000000-0000-0000-0000-000000000000/messages", headers: headers
    expect(response).to have_http_status(:not_found)
    expect(json['errors'].first['code']).to eq('conversation_not_found')
  end
end
