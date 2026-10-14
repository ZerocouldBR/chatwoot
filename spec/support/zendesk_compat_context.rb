# Dados de teste da API de compatibilidade com o Zendesk (M7), no formato da importação (docs/IMPORTACAO.md):
# ticket importado com display_id = nº do Zendesk, contato zd:<id>, agentes com zendesk_user_id, campos zd_*.
# Nomes, e-mails e telefones são fictícios; IDs de campo, grupo e status são os da conta B2B (config/servicedesk/zendesk_compat.json).
# rubocop:disable RSpec/MultipleMemoizedHelpers, Metrics/ParameterLists, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
RSpec.shared_context 'with zendesk compat data' do
  let(:ai_agent_zid) { 36_212_918_767_515 }
  let(:support_group_zid) { 20_487_412_043_675 }
  let(:tabulacao_field_id) { 21_537_600_796_443 }
  let(:account) { create(:account) }
  let(:cema) do
    create(:user, account: account, role: :administrator, name: 'Cema', email: 'agenteia.suporte@example.com',
                  custom_attributes: { 'zendesk_user_id' => ai_agent_zid.to_s })
  end
  let(:human_agent) do
    create(:user, account: account, role: :agent, name: 'Agente Humano', email: 'agente.humano@example.com',
                  custom_attributes: { 'zendesk_user_id' => '21000000000001' })
  end
  let(:support_team) { create(:team, account: account, name: 'suporte') }
  let(:email_channel) { create(:channel_email, account: account, email: 'atendimentob2b@example.com') }
  let(:email_inbox) { email_channel.inbox }
  let(:api_inbox) { create(:inbox, account: account, name: 'WhatsApp', channel: create(:channel_api, account: account)) }
  let(:company) { create(:company, account: account, name: 'Hotel Exemplo', custom_attributes: { 'zd_org_id' => '21300000000001' }) }
  let(:requester) do
    create(:contact, account: account, name: 'Reservas Hotel Exemplo', email: 'reservas@hotel-exemplo.com.br', phone_number: '+5511999990000',
                     identifier: 'zd:24033324330395', company_id: company.id,
                     custom_attributes: { 'zd_user_id' => '24033324330395', 'zd_cnpj' => '00.000.000/0001-00' })
  end
  let(:cc_contact) do
    create(:contact, account: account, name: 'Agência Exemplo', email: 'agencia@agencia-exemplo.com.br', identifier: 'zd:31255458137883')
  end
  let(:headers) { zendesk_basic_headers(cema) }

  let(:ticket) do
    support_team.add_members([human_agent.id, cema.id])
    cc_contact
    conversation = create_ticket(426_563, inbox: email_inbox, assignee: cema, status: :open,
                                          custom_attributes: { 'zd_status' => 'Aberto', 'zd_tabulacao' => 'Checkout - Estorno',
                                                               'zd_cc' => 'agencia@agencia-exemplo.com.br', 'zd_tipo' => 'Tarefa',
                                                               'zd_canal' => 'E-mail' },
                                          additional_attributes: { 'mail_subject' => 'Reserva 21429607 - cancelamento',
                                                                   'zendesk' => { 'via' => { 'channel' => 'email', 'source' => {
                                                                     'from' => { 'address' => 'reservas@hotel-exemplo.com.br',
                                                                                 'name' => 'Reservas Hotel Exemplo' },
                                                                     'to' => { 'address' => 'atendimentob2b@b2breservas.com.br',
                                                                               'name' => 'B2B Reservas' },
                                                                     'rel' => nil
                                                                   } } } })
    seed_native_fields(conversation, cc: 'agencia@agencia-exemplo.com.br', ticket_type: :task)
  end

  let(:chat_ticket) do
    create_ticket(427_406, inbox: api_inbox, assignee: cema, status: :open, custom_attributes: { 'zd_status' => 'Aberto', 'zd_canal' => 'WhatsApp' })
  end

  # Exemplos do modelo de ticket legado (zd_status/zd_cc/sd_ticket_audits) ficam pendentes no modelo nativo (f10), e
  # os que dependem dos status personalizados (config/servicedesk/ticket_statuses.yml) ficam pendentes num fork sem eles.
  before do |example|
    skip 'exemplo do modelo de ticket legado' if example.metadata[:legacy_ticket_model] && ZendeskCompat::TicketModel.native?
    skip 'fork sem status personalizados' if example.metadata[:custom_statuses] && !ZendeskCompat::TicketModel.labels?
  end

  before do
    ENV['ZENDESK_COMPAT_ENABLED'] = 'true'
    create(:custom_attribute_definition, account: account, attribute_model: 'conversation_attribute', attribute_key: 'zd_tabulacao',
                                         attribute_display_type: 'list', attribute_description: "zendesk_field:#{tabulacao_field_id}",
                                         attribute_values: ['Checkout - Estorno', 'Cancelamento Interno'])
  end

  after { ENV.delete('ZENDESK_COMPAT_ENABLED') }

  # status do modelo de ticket do fork para uma categoria do Zendesk
  def status_for(category)
    native = { open: :open, pending: :waiting_on_customer, hold: :on_hold, solved: :resolved }
    legacy = { open: :open, pending: :snoozed, hold: :snoozed, solved: :resolved }
    (ZendeskCompat::TicketModel.native? ? native : legacy).fetch(category)
  end

  # No modelo nativo o assunto, o tipo e os CCs ficam em colunas/tabela próprias (os zd_* do seed não valem).
  def seed_native_fields(conversation, cc: nil, ticket_type: nil)
    return conversation unless ZendeskCompat::TicketModel.native?

    conversation.update!(subject: conversation.additional_attributes['mail_subject'], ticket_type: ticket_type)
    conversation.conversation_ccs.create!(account_id: conversation.account_id, email: cc) if cc
    conversation.reload
  end

  def zendesk_basic_headers(user, token: user.access_token.token)
    { 'Authorization' => ActionController::HttpAuthentication::Basic.encode_credentials("#{user.email}/token", token) }
  end

  def json_headers
    headers.merge('Content-Type' => 'application/json', 'Accept' => 'application/json')
  end

  def create_ticket(display_id, inbox:, assignee: nil, status: :open, custom_attributes: {}, additional_attributes: {})
    contact_inbox = ContactInbox.find_by(contact: requester, inbox: inbox) ||
                    create(:contact_inbox, contact: requester, inbox: inbox, source_id: inbox.email? ? requester.email : SecureRandom.uuid)
    conversation = create(:conversation, account: account, inbox: inbox, contact: requester, contact_inbox: contact_inbox, assignee: assignee,
                                         team: support_team, status: status, identifier: "zd:#{display_id}",
                                         custom_attributes: custom_attributes, additional_attributes: additional_attributes)
    conversation.update_columns(display_id: display_id) # rubocop:disable Rails/SkipsModelValidations
    conversation.update_labels(%w[cancelamento atendimento_ia])
    conversation.reload
  end

  def add_message(conversation, type:, content:, sender:, private: false, attachment: nil, created_at: Time.current)
    message = build(:message, account: account, inbox: conversation.inbox, conversation: conversation, message_type: type,
                              content: content, sender: sender, private: private, created_at: created_at)
    message.attachments.new(account_id: account.id, file_type: :file, file: attachment) if attachment
    message.save!
    message
  end

  def ticket_with_history
    add_message(ticket, type: :incoming, content: 'Bom dia, preciso cancelar a reserva 21429607.', sender: requester, created_at: 2.hours.ago)
    add_message(ticket, type: :outgoing, content: 'Nota: cliente pediu cancelamento.', sender: human_agent, private: true, created_at: 90.minutes.ago)
    add_message(ticket, type: :outgoing, content: 'Olá! Sua solicitação foi recebida.', sender: cema, created_at: 1.hour.ago,
                        attachment: fixture_file_upload(Rails.root.join('spec/assets/sample.pdf'), 'application/pdf'))
    ticket
  end

  def json
    response.parsed_body
  end

  # Confere se um caminho como "comments[].attachments[].content_url" existe na resposta (a chave existe; o valor pode ser nulo).
  # "lista[]" = todos os itens têm o resto do caminho; "lista[*]" = algum item tem.
  def path_present?(data, path)
    head, rest = path.split('.', 2)
    mode = if head.end_with?('[]') then :all
           elsif head.end_with?('[*]') then :any
           end
    key = head.sub(/\[\*?\]\z/, '')
    return false unless data.is_a?(Hash) && data.key?(key)

    value = data[key]
    return mode.nil? || value.is_a?(Array) if rest.nil?
    return path_present?(value, rest) if mode.nil?
    return false if !value.is_a?(Array) || value.empty?

    mode == :all ? value.all? { |item| path_present?(item, rest) } : value.any? { |item| path_present?(item, rest) }
  end
end
# rubocop:enable RSpec/MultipleMemoizedHelpers, Metrics/ParameterLists, Metrics/CyclomaticComplexity, Metrics/PerceivedComplexity
