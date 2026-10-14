# Dados FICTÍCIOS para o e2e da API de compatibilidade com o Zendesk (M7) num banco de DESENVOLVIMENTO.
# Uso: ZENDESK_COMPAT_E2E_TOKEN=<token> bundle exec rails runner db/seeds/servicedesk_zendesk_compat_e2e.rb
# Idempotente (rodar de novo volta os tickets ao estado inicial). Cria (ou reaproveita) a conta "B2B e2e M7", a usuária
# de integração Cema (admin, zendesk_user_id do AI agent dos workflows) com o token informado, um agente, o time
# "suporte" (grupo 20487412043675), uma caixa API (sem envio real) e os tickets 426563 (e-mail, histórico) e 427406 (chat).
# Nunca rode em produção.
# rubocop:disable Metrics/ParameterLists, Rails/Output
abort('Somente em development/test') if Rails.env.production?

token = ENV.fetch('ZENDESK_COMPAT_E2E_TOKEN')
account = Account.find_or_create_by!(name: 'B2B e2e M7')

def e2e_user(account, email, name, role, zid)
  user = User.from_email(email) || User.new(email: email, name: name, password: "E2e!#{SecureRandom.hex(12)}")
  user.skip_confirmation!
  user.update!(name: name, custom_attributes: (user.custom_attributes || {}).merge('zendesk_user_id' => zid))
  AccountUser.find_or_create_by!(account: account, user: user) { |au| au.role = role }.update!(role: role)
  user
end

cema = e2e_user(account, 'agenteia.suporte.e2e@example.com', 'Cema', :administrator, '36212918767515')
cema.access_token.update!(token: token)
agent = e2e_user(account, 'agente.humano.e2e@example.com', 'Agente Humano', :agent, '21000000000001')
team = account.teams.where('LOWER(name) = ?', 'suporte').first || account.teams.create!(name: 'suporte')
team.add_members([cema.id, agent.id] - team.members.ids)

inbox = account.inboxes.find_by(name: 'E2E API') ||
        account.inboxes.create!(name: 'E2E API', channel: Channel::Api.create!(account: account))
inbox.update!(enable_auto_assignment: false)
[cema, agent].each { |user| InboxMember.find_or_create_by!(inbox: inbox, user: user) }

account.custom_attribute_definitions.find_or_create_by!(attribute_key: 'zd_tabulacao', attribute_model: 'conversation_attribute') do |cad|
  cad.attribute_display_name = 'Tabulação'
  cad.attribute_display_type = 'list'
  cad.attribute_description = 'zendesk_field:21537600796443'
  cad.attribute_values = ['Checkout - Estorno', 'Cancelamento Interno']
end

company = account.companies.find_or_create_by!(name: 'Hotel Exemplo e2e') { |c| c.custom_attributes = { 'zd_org_id' => '21300000000001' } }
requester = account.contacts.find_or_create_by!(identifier: 'zd:24033324330395') do |contact|
  contact.name = 'Reservas Hotel Exemplo'
  contact.email = 'reservas.e2e@hotel-exemplo.example'
  contact.company_id = company.id
  contact.custom_attributes = { 'zd_user_id' => '24033324330395' }
end
account.contacts.find_or_create_by!(identifier: 'zd:31255458137883') do |contact|
  contact.name = 'Agência Exemplo'
  contact.email = 'agencia.e2e@agencia-exemplo.example'
end

def e2e_ticket(account, inbox, requester, team, assignee, display_id, attrs)
  existing = account.conversations.find_by(display_id: display_id)
  if existing # nova rodada do e2e: volta ao estado inicial (aberto, responsável e campos do seed, sem etiquetas)
    existing.update!(status: :open, assignee: assignee, team: team, custom_attributes: attrs[:custom_attributes], label_list: [])
    return existing
  end

  contact_inbox = ContactInbox.find_or_create_by!(contact: requester, inbox: inbox) { |ci| ci.source_id = SecureRandom.uuid }
  conversation = Conversation.create!(account: account, inbox: inbox, contact: requester, contact_inbox: contact_inbox, team: team,
                                      assignee: assignee, status: :open, identifier: "zd:#{display_id}", **attrs)
  conversation.update_columns(display_id: display_id) # rubocop:disable Rails/SkipsModelValidations
  conversation.reload
end

Current.user = cema
email_ticket = e2e_ticket(account, inbox, requester, team, cema, 426_563,
                          custom_attributes: { 'zd_status' => 'Aberto', 'zd_tabulacao' => 'Checkout - Estorno', 'zd_canal' => 'E-mail',
                                               'zd_cc' => 'agencia.e2e@agencia-exemplo.example' },
                          additional_attributes: { 'mail_subject' => 'Reserva 21429607 - cancelamento',
                                                   'zendesk' => { 'via' => { 'channel' => 'email', 'source' => {
                                                     'from' => { 'address' => requester.email, 'name' => requester.name },
                                                     'to' => { 'address' => 'atendimentob2b@b2breservas.com.br', 'name' => 'B2B' }, 'rel' => nil
                                                   } } } })
chat_ticket = e2e_ticket(account, inbox, requester, team, cema, 427_406, custom_attributes: { 'zd_status' => 'Aberto', 'zd_canal' => 'WhatsApp' })

# Modelo de ticket nativo (feat/tickets-f10): assunto e CCs em coluna/tabela próprias.
if ZendeskCompat::TicketModel.native?
  email_ticket.update!(subject: 'Reserva 21429607 - cancelamento')
  ZendeskCompat::TicketModel.write_cc_emails(email_ticket, ['agencia.e2e@agencia-exemplo.example'])
end

if email_ticket.messages.empty?
  email_ticket.messages.create!(account: account, inbox: inbox, message_type: :incoming, sender: requester,
                                content: 'Bom dia, preciso cancelar a reserva 21429607.')
  email_ticket.messages.create!(account: account, inbox: inbox, message_type: :outgoing, sender: agent, private: true,
                                content: 'Nota: cliente pediu cancelamento.')
end
if chat_ticket.messages.empty?
  chat_ticket.messages.create!(account: account, inbox: inbox, message_type: :incoming, sender: requester,
                               content: 'Oi, quero cancelar')
end
Current.reset

puts({ account_id: account.id, cema: cema.email, email_ticket: email_ticket.display_id, chat_ticket: chat_ticket.display_id,
       chat_conversation_uuid: chat_ticket.uuid, sunco_user_id: ZendeskCompat::ConversationLogBuilder.sunco_user_id(requester) }.to_json)
# rubocop:enable Metrics/ParameterLists, Rails/Output
