require 'rails_helper'

# API de compatibilidade sobre o modelo de ticket NATIVO (feat/tickets-f0..f10: enum de status do Zendesk, subject,
# ticket_type, due_at, company_id, submitter_id, conversation_ccs e conversation_events). Na servicedesk/main (modelo
# legado) estes exemplos ficam pendentes; na base f10 eles rodam.
RSpec.describe 'Zendesk compat: modelo de ticket nativo (f10)', type: :request do
  include_context 'with zendesk compat data'

  before { skip 'modelo de ticket legado (sem o enum de status do Zendesk)' unless ZendeskCompat::TicketModel.native? }

  let(:native_ticket) do
    support_team.add_members([cema.id, human_agent.id])
    ticket.update!(status: :open, subject: 'Reserva 21429607 - cancelamento', ticket_type: :task, due_at: Time.zone.parse('2026-10-20T15:00:00Z'))
    ticket.reload
  end

  def put_ticket(payload)
    put "/api/v2/tickets/#{native_ticket.display_id}.json", params: { ticket: payload }.to_json, headers: json_headers
  end

  it 'lê status, assunto, tipo e vencimento das colunas do modelo' do
    get "/api/v2/tickets/#{native_ticket.display_id}.json", headers: headers
    expect(json['ticket']).to include('status' => 'open', 'subject' => 'Reserva 21429607 - cancelamento', 'type' => 'task',
                                      'due_at' => '2026-10-20T15:00:00Z')
  end

  it 'grava status do Zendesk no enum (pending -> waiting_on_customer, hold -> on_hold, solved -> resolved)' do
    { 'pending' => 'waiting_on_customer', 'hold' => 'on_hold', 'solved' => 'resolved' }.each do |zendesk, native|
      put_ticket(status: zendesk)
      expect(response).to have_http_status(:ok), response.body
      expect(native_ticket.reload.status).to eq(native)
      expect(json.dig('ticket', 'status')).to eq(zendesk)
    end
  end

  it 'grava assunto, tipo e vencimento nas colunas' do
    put_ticket(subject: 'Novo assunto', type: 'task', due_at: '2026-11-01T12:00:00Z')
    native_ticket.reload
    expect(native_ticket.subject).to eq('Novo assunto')
    expect(native_ticket.ticket_type).to eq('task')
    expect(native_ticket.due_at).to eq(Time.zone.parse('2026-11-01T12:00:00Z'))
  end

  it 'usa conversation_ccs para email_ccs (leitura e escrita)' do
    put_ticket(email_ccs: [{ user_email: 'agencia@agencia-exemplo.com.br', action: 'put' }, { user_email: 'nova@example.com', action: 'put' }])
    expect(native_ticket.conversation_ccs.pluck(:email)).to contain_exactly('agencia@agencia-exemplo.com.br', 'nova@example.com')

    put_ticket(email_ccs: [{ user_email: 'nova@example.com', action: 'delete' }])
    expect(native_ticket.conversation_ccs.pluck(:email)).to eq(['agencia@agencia-exemplo.com.br'])
    get "/api/v2/tickets/#{native_ticket.display_id}/email_ccs.json", headers: headers
    expect(json['users'].pluck('email')).to eq(['agencia@agencia-exemplo.com.br'])
  end

  it 'monta os audits a partir de conversation_events, com nomes e valores do Zendesk' do
    put_ticket(assignee_id: 21_000_000_000_001, status: 'pending')
    expect(json.dig('audit', 'events')).to include(include('field_name' => 'assignee_id', 'value' => '21000000000001',
                                                           'previous_value' => ai_agent_zid.to_s),
                                                   include('field_name' => 'status', 'value' => 'pending', 'previous_value' => 'open'))

    get "/api/v2/tickets/#{native_ticket.display_id}/audits.json?page[size]=100", headers: headers
    events = json['audits'].flat_map { |audit| audit['events'] }
    expect(events).to include(include('type' => 'Create', 'field_name' => 'status'))
    expect(events).to include(include('type' => 'Change', 'field_name' => 'assignee_id', 'value' => '21000000000001'))
    expect(Servicedesk::TicketAudit.where(conversation_id: native_ticket.id)).to be_empty
  end

  it 'busca pela categoria do enum' do
    native_ticket.update!(status: :on_hold)
    get "/api/v2/search.json?#{{ query: 'type:ticket status:hold' }.to_query}", headers: headers
    expect(json['results'].pluck('id')).to eq([native_ticket.display_id])
    get "/api/v2/search.json?#{{ query: 'type:ticket status<hold' }.to_query}", headers: headers
    expect(json['results'].pluck('id')).not_to include(native_ticket.display_id)
  end
end
