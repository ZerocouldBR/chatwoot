# rubocop:disable Metrics/AbcSize, Metrics/CyclomaticComplexity
require 'rails_helper'

# Teste de contrato por workflow do n8n: cada chamada que o workflow faz hoje ao Zendesk (fixture tirada da exportação)
# é feita na API de compatibilidade, pelo prefixo /b2b-reservas.zendesk.com, e a resposta precisa ter todos os campos
# que o workflow lê. Ver spec/fixtures/zendesk_compat/workflow_contracts.yml e docs/ZENDESK-COMPAT-API.md.
RSpec.describe 'Zendesk compat: contrato dos workflows do n8n', type: :request do
  include_context 'with zendesk compat data'

  contracts = YAML.safe_load_file(Rails.root.join('spec/fixtures/zendesk_compat/workflow_contracts.yml'))['workflows']
  prefix = '/b2b-reservas.zendesk.com'

  let(:placeholders) do
    ticket_with_history
    add_message(chat_ticket, type: :incoming, content: 'Oi, quero cancelar', sender: requester, created_at: 10.minutes.ago)
    add_message(chat_ticket, type: :outgoing, content: 'Claro! Qual o localizador?', sender: cema, created_at: 9.minutes.ago)
    blob = ZendeskCompat::Uploads.create(io: StringIO.new('%PDF-1.4 teste'), filename: 'comprovante.pdf', content_type: 'application/pdf')
    attachment_url = ticket.messages.joins(:attachments).first.attachments.first
    {
      'ticket_id' => ticket.display_id, 'chat_ticket_id' => chat_ticket.display_id, 'ai_agent_id' => ai_agent_zid,
      'agent_id' => 21_000_000_000_001, 'group_id' => support_group_zid, 'requester_id' => 24_033_324_330_395,
      'cc_user_id' => 31_255_458_137_883, 'conversation_id' => chat_ticket.uuid,
      'sunco_user_id' => ZendeskCompat::ConversationLogBuilder.sunco_user_id(requester),
      'upload_token' => ZendeskCompat::Uploads.token(blob),
      'content_url' => URI(Rails.application.routes.url_helpers.rails_blob_url(attachment_url.file.blob, host: 'www.example.com')).path
    }
  end

  def fill(value, values)
    case value
    when Hash then value.transform_values { |item| fill(item, values) }
    when Array then value.map { |item| fill(item, values) }
    when String
      whole = value.match(/\A\{(\w+)\}\z/)
      return values.fetch(whole[1]) if whole && values[whole[1]].is_a?(Integer)

      value.gsub(/\{(\w+)\}/) { values.fetch(Regexp.last_match(1)).to_s }
    else value
    end
  end

  def perform_call(call, values, prefix)
    path = fill(call['path'], values)
    path = "#{prefix}#{path}" if path.start_with?('/api/', '/sc/')
    query = fill(call['query'] || {}, values)
    url = query.any? ? "#{path}?#{query.to_query}" : path
    if call['upload']
      post url, params: File.binread(Rails.root.join('spec/assets/sample.pdf')), headers: headers.merge('Content-Type' => 'application/pdf')
    elsif call['sunshine_upload']
      post url, params: { source: fixture_file_upload(Rails.root.join('spec/assets/sample.png'), 'image/png') }, headers: headers
    else
      body = call['body'] ? fill(call['body'], values).to_json : nil
      public_send(call['method'].downcase, url, params: body, headers: json_headers)
    end
  end

  contracts.each do |workflow|
    it "atende o workflow \"#{workflow['name']}\" (#{workflow['calls'].size} chamada(s))" do
      values = placeholders
      workflow['calls'].each do |call|
        perform_call(call, values, prefix)
        expected = call['status'] || 200
        expect(response.status).to eq(expected),
                                   "#{call['node']}: #{call['method']} #{call['path']} -> #{response.status} #{response.body.first(300)}"
        next if call['reads'].blank?

        missing = call['reads'].reject { |path| path_present?(json, path) }
        expect(missing).to be_empty, "#{call['node']}: campos ausentes #{missing} em #{response.body.first(500)}"
      end
    end
  end
end
# rubocop:enable Metrics/AbcSize, Metrics/CyclomaticComplexity
