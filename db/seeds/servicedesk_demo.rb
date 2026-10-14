# frozen_string_literal: true

# ServiceDesk: dados de DEMONSTRAÇÃO para o ambiente de desenvolvimento (verificação visual do layout).
#
#   bundle exec rails runner db/seeds/servicedesk_demo.rb
#   (dev da VPS: /opt/servicedesk-dev/dev.sh rails runner db/seeds/servicedesk_demo.rb)
#
# LGPD: todos os nomes, e-mails, organizações e textos são FICTÍCIOS (domínios .test, RFC 2606). Nada vem do
# Zendesk real além das DEFINIÇÕES de campos (zendesk_field_map.json, sem dados pessoais) e dos formulários
# versionados em app/javascript/dashboard/servicedesk/ticketForms*.json.
#
# Variáveis de ambiente (opcionais):
#   SD_FIELD_MAP            zendesk_field_map.json (padrão tmp/servicedesk_demo/zendesk_field_map.json). Sem ele,
#                           cria só um conjunto mínimo de campos zd_*.
#   SD_DEMO_PASSWORD_FILE   onde gravar a senha do admin de teste, UMA vez, com permissão 600
#                           (padrão tmp/servicedesk_demo/dev-admin.txt). A senha nunca vai para o stdout.
#   SD_DEMO_RESET_PASSWORD  =1 gera uma senha nova para o admin (grava de novo no arquivo).
#
# Idempotente: conta, usuários, times, inboxes, campos e etiquetas por chave natural; contatos por identifier
# 'zd:<id>'; tickets por display_id (990001..990040, faixa reservada à demo). Bulk via insert_all/upsert_all
# (sem callbacks: nenhum e-mail, notificação, webhook ou job). Termina com SD_DEMO_OK ou SD_DEMO_FALHA.
#
# rubocop:disable Rails/Output -- script de console: o resultado (OK/FALHA) vai para o stdout de propósito
# rubocop:disable Rails/SkipsModelValidations -- bulk sem callbacks é regra do projeto (dormência)
require 'json'
require 'securerandom'

db_name = ActiveRecord::Base.connection.current_database
abort "SD_DEMO_FALHA: só roda em development (RAILS_ENV=#{Rails.env})" unless Rails.env.development?
abort "SD_DEMO_FALHA: banco '#{db_name}' protegido (demo/staging)" if %w[chatwoot chatwoot_staging chatwoot_production].include?(db_name)

ACCOUNT_NAME = 'ServiceDesk Demo'
ADMIN_EMAIL = 'admin.demo@servicedesk.test'
DISPLAY_BASE = 990_000
NOW = Time.current
RNG = Random.new(20_261_013)
FIELD_MAP_PATH = ENV.fetch('SD_FIELD_MAP', Rails.root.join('tmp/servicedesk_demo/zendesk_field_map.json').to_s)
PASSWORD_FILE = ENV.fetch('SD_DEMO_PASSWORD_FILE', Rails.root.join('tmp/servicedesk_demo/dev-admin.txt').to_s)
FORMS = JSON.parse(Rails.root.join('app/javascript/dashboard/servicedesk/ticketForms.json').read)
FORMS_META = JSON.parse(Rails.root.join('app/javascript/dashboard/servicedesk/ticketFormsMeta.json').read)
STATS = Hash.new(0)

ENQUEUED = [] # rubocop:disable Style/MutableConstant
ActiveSupport::Notifications.subscribe(/\Aenqueue(_at|_all)?\.active_job\z/) do |*, payload|
  (payload[:jobs] || [payload[:job]]).compact.each { |j| ENQUEUED << j.class.name }
end

def strong_password
  # regra do Chatwoot: maiúscula, minúscula, número e caractere especial
  "Sd#{SecureRandom.base58(18)}!#{RNG.rand(10..99)}aZ"
end

# ------------------------------------------------------------------ branding (só no banco de dev)
{ 'INSTALLATION_NAME' => 'ServiceDesk', 'BRAND_NAME' => 'ServiceDesk',
  'LOGO' => '/brand-assets/servicedesk_logo.svg', 'LOGO_DARK' => '/brand-assets/servicedesk_logo_dark.svg',
  'LOGO_THUMBNAIL' => '/brand-assets/servicedesk_logo_thumbnail.svg' }.each do |name, value|
  config = InstallationConfig.find_or_initialize_by(name: name)
  next if config.value == value

  config.value = value
  config.save!
  STATS['branding_ajustado'] += 1
end
GlobalConfig.clear_cache

# ------------------------------------------------------------------ conta e usuários
account = Account.find_or_create_by!(name: ACCOUNT_NAME) { |a| a.locale = 'pt_BR' }
account.update!(locale: 'pt_BR') unless account.locale == 'pt_BR'

admin = User.from_email(ADMIN_EMAIL)
new_password = nil
if admin.nil? || ENV['SD_DEMO_RESET_PASSWORD'] == '1'
  new_password = strong_password
  admin ||= User.new(email: ADMIN_EMAIL, name: 'Admin Demo')
  admin.password = new_password
  admin.password_confirmation = new_password
  admin.skip_confirmation!
  admin.save!
  STATS['admin_senha_gerada'] += 1
end
AccountUser.find_or_create_by!(account: account, user: admin) { |au| au.role = :administrator }

AGENTS = [
  ['Bruna Exemplo', 'bruna.exemplo'], ['Carlos Ficticio', 'carlos.ficticio'], ['Daniela Teste', 'daniela.teste'],
  ['Eduardo Modelo', 'eduardo.modelo'], ['Fernanda Amostra', 'fernanda.amostra'], ['Gustavo Demo', 'gustavo.demo']
].map do |name, login|
  user = User.from_email("#{login}@servicedesk.test")
  unless user
    user = User.new(email: "#{login}@servicedesk.test", name: name, password: strong_password)
    user.skip_confirmation!
    user.save!
    STATS['agentes_criados'] += 1
  end
  AccountUser.find_or_create_by!(account: account, user: user) { |au| au.role = :agent }
  user
end

# ------------------------------------------------------------------ 31 times fictícios (dormentes)
TEAM_NAMES = [
  'Atendimento Geral', 'Atendimento Agências', 'Atendimento Hotéis', 'Atendimento Corporativo', 'Suporte N1', 'Suporte N2',
  'Suporte N3', 'Sustentação', 'Integrações', 'Infraestrutura', 'Qualidade', 'Produto', 'Desenvolvimento',
  'Financeiro', 'Faturamento', 'Cobrança', 'Contas a Pagar', 'Cadastro', 'Alterações de Cadastro', 'Tarifas',
  'Pagamentos', 'Checkout', 'Comercial', 'Customer Success', 'Onboarding', 'Treinamento', 'Relacionamento',
  'Ouvidoria', 'Jurídico', 'Segurança da Informação', 'Equipe Argentina'
].freeze
teams = TEAM_NAMES.map do |name|
  # nome como digitado (o Team não força mais minúsculas); acha o time antigo
  # salvo em minúsculas e corrige o nome
  team = account.teams.find_by('LOWER(name) = ?', name.downcase) || account.teams.new
  STATS['times_criados'] += 1 if team.new_record?
  team.name = name
  team.description = 'Time fictício (demo)'
  team.allow_auto_assign = false
  team.save! if team.changed? # sem mudança = sem callbacks/jobs
  team
end

# ------------------------------------------------------------------ inboxes (dormentes)
def ensure_api_inbox(account, name)
  inbox = account.inboxes.find_by(name: name)
  return inbox if inbox

  channel = Channel::Api.create!(account: account, webhook_url: nil)
  STATS['inboxes_criadas'] += 1
  account.inboxes.create!(name: name, channel: channel, enable_auto_assignment: false, greeting_enabled: false,
                          csat_survey_enabled: false)
end

def ensure_email_inbox(account, name, email)
  channel = Channel::Email.find_by(email: email.downcase) # rubocop:disable UseFromEmail -- canal, não usuário
  unless channel
    channel = Channel::Email.create!(account: account, email: email, imap_enabled: false, smtp_enabled: false)
    STATS['inboxes_criadas'] += 1
    account.inboxes.create!(name: name, channel: channel)
  end
  channel.assign_attributes(imap_enabled: false, smtp_enabled: false)
  channel.save! if channel.changed?
  inbox = channel.inbox
  inbox.assign_attributes(enable_auto_assignment: false, greeting_enabled: false, csat_survey_enabled: false)
  inbox.save! if inbox.changed?
  inbox
end

EMAIL_INBOXES = [
  ensure_email_inbox(account, 'Relacionamento (demo)', 'relacionamento@empresa-demo.test'),
  ensure_email_inbox(account, 'Suporte (demo)', 'suporte@empresa-demo.test'),
  ensure_email_inbox(account, 'Financeiro (demo)', 'financeiro@empresa-demo.test')
].freeze
API_INBOXES = {
  'whatsapp' => 'WhatsApp (histórico)', 'native_messaging' => 'Mensagens (histórico)',
  'web' => 'Web/Formulário (histórico)', 'api' => 'API (histórico)'
}.transform_values { |name| ensure_api_inbox(account, name) }

# ------------------------------------------------------------------ campos zd_* (definições)
def ensure_definition(account, key:, model:, type:, name:, description:, values:) # rubocop:disable Metrics/ParameterLists
  cad = account.custom_attribute_definitions.find_or_initialize_by(attribute_key: key, attribute_model: model)
  STATS["campos_criados_#{model}"] += 1 if cad.new_record?
  cad.attribute_display_name = name
  cad.attribute_display_type = type
  cad.attribute_description = description
  cad.attribute_values = type == 'list' ? Array(values).compact.uniq : []
  cad.save! if cad.changed?
  cad
end

if File.exist?(FIELD_MAP_PATH)
  map = JSON.parse(File.read(FIELD_MAP_PATH))
  ui = map['ui_names'] || {}
  inactive_suffix = ui['inactive_suffix'] || ' (inativo)'
  renamed = ui['renamed_values'] || {}
  rename = ->(key, values) { values&.map { |v| renamed.dig(key, v) || v } }
  map['ticket_fields'].each do |zid, f|
    next if f['system'] || !f['provision']

    values = f['type'] == 'list' ? f['options'].values + (f['historical_options'] || {}).values : nil
    name = f['active'] ? f['title'].strip : "#{f['title'].strip}#{inactive_suffix}"
    ensure_definition(account, key: f['key'], model: 'conversation_attribute', type: f['type'], name: name,
                               description: "zendesk_field:#{zid}", values: values)
  end
  map['extra_definitions'].each do |d|
    ensure_definition(account, key: d['key'], model: d['model'], type: d['type'], name: d['name'],
                               description: d['description'], values: rename.call(d['key'], d['values']))
  end
  tipo_id, tipo = map['ticket_fields'].find { |_, f| f['zendesk_type'] == 'tickettype' }
  defs = ui['definitions'] || {}
  [['zd_status', 'list', 'zendesk:custom_status', map['zd_status_values']],
   ['zd_formulario', 'list', 'zendesk:ticket_form', map['zd_formulario_values']],
   ['zd_ticket_id', 'number', 'zendesk:ticket_id', nil],
   ['zd_tipo', 'list', "zendesk_field:#{tipo_id}", tipo['options'].values]].each do |key, type, desc, values|
    ensure_definition(account, key: key, model: 'conversation_attribute', type: type,
                               name: defs.fetch(key, key), description: desc, values: values)
  end
  [%w[user_fields_detail user_field_options contact_attribute zendesk_user_field],
   %w[org_fields_detail org_field_options company_attribute zendesk_org_field]].each do |det, opt, model, prefix|
    map[det].each do |zkey, d|
      next unless d['provision'] && d['attr']
      next if map['extra_definitions'].any? { |x| x['key'] == d['attr'] && x['model'] == model }

      values = d['type'] == 'list' ? (map[opt][zkey] || {}).values : nil
      ensure_definition(account, key: d['attr'], model: model, type: d['type'], name: d['title'].strip,
                                 description: "#{prefix}:#{d['id']}", values: values)
    end
  end
else
  puts "aviso: #{FIELD_MAP_PATH} não encontrado; criando só os campos mínimos"
  [['zd_status', 'list', 'Status do ticket', 'zendesk:custom_status', FORMS_META['statuses'].keys],
   ['zd_formulario', 'list', 'Formulário', 'zendesk:ticket_form', FORMS_META['forms'].keys],
   ['zd_ticket_id', 'number', 'Nº do ticket (histórico)', 'zendesk:ticket_id', nil],
   ['zd_tipo', 'list', 'Tipo', 'zendesk_field:20487384447387', %w[Pergunta Incidente Problema Tarefa]],
   ['zd_area_interna', 'list', 'Área interna', 'zendesk_field:21587135564955', %w[Suporte Financeiro Hospitality]],
   ['zd_cc', 'text', 'CC (e-mails)', 'zendesk:email_cc_ids', nil],
   ['zd_seguidores', 'text', 'Seguidores (e-mails)', 'zendesk:follower_ids', nil]].each do |key, type, name, desc, values|
    ensure_definition(account, key: key, model: 'conversation_attribute', type: type, name: name,
                               description: desc, values: values)
  end
end

CONV_DEFS = account.custom_attribute_definitions.where(attribute_model: :conversation_attribute).to_a
DEF_BY_FIELD = CONV_DEFS.each_with_object({}) do |d, h|
  h[d.attribute_description.delete_prefix('zendesk_field:')] = d if d.attribute_description.to_s.start_with?('zendesk_field:')
end
DEF_BY_KEY = CONV_DEFS.index_by(&:attribute_key)

# ------------------------------------------------------------------ etiquetas
LABELS = %w[vip retorno-cliente aguardando-financeiro integracao reserva-urgente boleto voucher treinamento].freeze
Label.insert_all(LABELS.map { |t| { account_id: account.id, title: t, color: '#1F73B7', show_on_sidebar: false, created_at: NOW, updated_at: NOW } },
                 unique_by: %i[title account_id])
ActsAsTaggableOn::Tag.insert_all(LABELS.map { |n| { name: n } }, unique_by: :name)
TAG_IDS = ActsAsTaggableOn::Tag.where(name: LABELS).pluck(:name, :id).to_h

# ------------------------------------------------------------------ contatos fictícios
FIRST = %w[Ana Bruno Camila Diego Elisa Fabio Gabriela Heitor Isabela Joao Karina Leonardo Mariana Nicolas Olivia Paulo
           Renata Sergio Tatiana Vinicius].freeze
LAST = %w[Exemplo Ficticio Teste Modelo Amostra Demo Simulado Prototipo].freeze
ORGS = ['Hotel Aurora Fictício', 'Pousada Brisa Demo', 'Agência Viagens Exemplo', 'Turismo Modelo Ltda',
        'Rede Hoteleira Amostra', 'Operadora Simulada', 'Resort Teste do Sol', nil].freeze
contact_rows = Array.new(24) do |i|
  first = FIRST[i % FIRST.size]
  last = LAST[i % LAST.size]
  org = ORGS[i % ORGS.size]
  zd_user = 9_100_000_000 + i
  login = "#{I18n.transliterate(first).downcase}.#{I18n.transliterate(last).downcase}#{i}"
  { account_id: account.id, name: "#{first} #{last}", email: "#{login}@cliente-demo.test",
    phone_number: format('+55119%08d', 10_000_000 + i), identifier: "zd:#{zd_user}", contact_type: 2,
    additional_attributes: { 'company_name' => org, 'source' => 'demo' }.compact,
    custom_attributes: { 'zd_user_id' => zd_user }, last_activity_at: NOW, created_at: NOW - 90.days, updated_at: NOW }
end
Contact.upsert_all(contact_rows, unique_by: %i[identifier account_id], record_timestamps: false)
CONTACTS = Contact.where(account_id: account.id, identifier: contact_rows.pluck(:identifier)).order(:identifier).to_a

# ------------------------------------------------------------------ tickets fictícios
ACTIVE_STATUSES = FORMS_META['statuses'].select { |_, s| s['active'] }.keys
STATUS_PLAN = (ACTIVE_STATUSES * 3).first(33) + ['Escalonado', 'Pendente Autenticação', nil, nil, nil, nil, nil]
NATIVE_FOR_BLANK = %w[open snoozed resolved pending open].freeze
PRIORITIES = [nil, 'low', 'medium', 'high', 'urgent'].freeze
FORM_PLAN = ['Atendimento', 'Formulário TI', 'LGPD & Segurança', nil].freeze
SUBJECTS = [
  'Voucher da reserva não chegou ao hóspede', 'Erro ao emitir boleto da fatura de setembro',
  'Dúvida sobre política de cancelamento do hotel', 'Integração com o PMS não atualiza tarifas',
  'Solicitação de segunda via de nota fiscal', 'Acesso bloqueado após autenticação em dois fatores',
  'Reserva duplicada no portal da agência', 'Alteração de dados bancários para repasse',
  'Tarifa não aparece na consulta como agência', 'Pedido de treinamento para nova equipe',
  'Link de pagamento expirado no checkout', 'Relatório de comissões com valores divergentes',
  'Cadastro de novo hotel na rede', 'Solicitação de exclusão de dados pessoais (teste)',
  'Instabilidade no envio de e-mails de confirmação', 'Ajuste de PDV e clientes vinculados'
].freeze
CHANNEL_PLAN = [['E-mail', :email], ['WhatsApp', 'whatsapp'], ['Mensagens', 'native_messaging'],
                ['Web (formulário/agente)', 'web'], ['API', 'api']].freeze
TICKET_TYPES = %w[Pergunta Incidente Problema Tarefa].freeze
STATUS_INT = { 'open' => 0, 'resolved' => 1, 'pending' => 2, 'snoozed' => 3 }.freeze
PRIORITY_INT = { 'low' => 0, 'medium' => 1, 'high' => 2, 'urgent' => 3 }.freeze

def fake_value(defn, idx)
  case defn.attribute_display_type
  when 'list' then defn.attribute_values.presence && defn.attribute_values[idx % defn.attribute_values.size]
  when 'checkbox' then idx.even?
  when 'number' then 1000 + idx
  when 'date' then (NOW - idx.days).iso8601
  when 'link' then "https://exemplo.test/item/#{idx}"
  else "Valor de exemplo #{idx}"
  end
end

# Valores de um ramo condicional do formulário (pai = valor da condição, filhos preenchidos).
def conditional_values(form, idx)
  conditions = FORMS_META.dig('conditions', form) || []
  return {} if conditions.empty?

  cond = conditions[idx % conditions.size]
  parent = DEF_BY_FIELD[cond['parent_field_id'].to_s]
  return {} unless parent

  values = { parent.attribute_key => cond['value'] }
  cond['child_fields'].each do |cf|
    d = DEF_BY_FIELD[cf['id'].to_s]
    values[d.attribute_key] = fake_value(d, idx) if d
  end
  values
end

def conditional_children(form)
  (FORMS_META.dig('conditions', form) || []).flat_map { |c| c['child_fields'].map { |cf| cf['id'].to_s } }.to_set
end

def fillable?(defn, values, seed)
  return false if defn.nil? || values.key?(defn.attribute_key) || defn.attribute_key == 'zd_tipo'

  seed % 3 != 2 && defn.attribute_display_name.exclude?('(inativo')
end

# Campos não condicionais do formulário (alguns ficam vazios de propósito).
def form_values(form, idx)
  values = conditional_values(form, idx)
  children = conditional_children(form)
  (FORMS[form] || []).map(&:to_s).reject { |fid| children.include?(fid) }.first(6).each_with_index do |fid, j|
    d = DEF_BY_FIELD[fid]
    next unless fillable?(d, values, idx + j)

    values[d.attribute_key] = fake_value(d, idx + j)
  end
  values.compact
end

ticket_plan = Array.new(40) do |i|
  zd_status = STATUS_PLAN[i]
  native = zd_status ? FORMS_META.dig('statuses', zd_status, 'native') : NATIVE_FOR_BLANK[i % NATIVE_FOR_BLANK.size]
  form = FORM_PLAN[i % FORM_PLAN.size]
  channel_label, channel_kind = CHANNEL_PLAN[i % CHANNEL_PLAN.size]
  inbox = channel_kind == :email ? EMAIL_INBOXES[i % EMAIL_INBOXES.size] : API_INBOXES.fetch(channel_kind)
  contact = CONTACTS[i % CONTACTS.size]
  updated = NOW - (i * 97).minutes - (i % 5).days
  custom = { 'zd_ticket_id' => DISPLAY_BASE + i + 1, 'zd_canal' => channel_label,
             'zd_tipo' => TICKET_TYPES[i % TICKET_TYPES.size],
             'zd_criado_em' => (updated - 2.days).iso8601, 'zd_atualizado_em' => updated.iso8601 }
  custom['zd_status'] = zd_status if zd_status
  custom['zd_formulario'] = form if form
  custom.merge!(form_values(form || FORMS_META['default_form'], i))
  custom['zd_cc'] = "copia#{i}@cliente-demo.test" if (i % 6).zero?
  custom['zd_seguidores'] = AGENTS[(i + 1) % AGENTS.size].email if (i % 7).zero?
  custom.select! { |k, _| DEF_BY_KEY.key?(k) }
  { i: i, native: native, inbox: inbox, contact: contact, custom: custom, updated: updated, email: channel_kind == :email,
    subject: "#{SUBJECTS[i % SUBJECTS.size]}#{i >= SUBJECTS.size ? " (#{(i / SUBJECTS.size) + 1})" : ''}",
    priority: PRIORITIES[i % PRIORITIES.size], team: teams[(i * 7) % teams.size],
    assignee: (i % 8) == 3 ? nil : AGENTS[i % AGENTS.size], labels: LABELS.rotate(i).first(i % 3) }
end

ci_rows = ticket_plan.map do |t|
  src = t[:email] ? t[:contact].email : "zd:#{t[:contact].custom_attributes['zd_user_id']}"
  t[:source_id] = src
  { contact_id: t[:contact].id, inbox_id: t[:inbox].id, source_id: src, created_at: NOW, updated_at: NOW }
end
ContactInbox.insert_all(ci_rows.uniq { |r| [r[:inbox_id], r[:source_id]] }, unique_by: %i[inbox_id source_id])
ci_ids = ContactInbox.where(inbox_id: ticket_plan.map { |t| t[:inbox].id }.uniq).pluck(:inbox_id, :source_id, :id)
                     .to_h { |iid, src, id| [[iid, src], id] }

conv_rows = ticket_plan.map do |t|
  { account_id: account.id, display_id: DISPLAY_BASE + t[:i] + 1, identifier: "zd:#{DISPLAY_BASE + t[:i] + 1}",
    inbox_id: t[:inbox].id, contact_id: t[:contact].id, contact_inbox_id: ci_ids.fetch([t[:inbox].id, t[:source_id]]),
    status: STATUS_INT.fetch(t[:native]), priority: t[:priority] && PRIORITY_INT[t[:priority]],
    assignee_id: t[:assignee]&.id, team_id: t[:team].id, custom_attributes: t[:custom],
    additional_attributes: { 'mail_subject' => t[:subject], 'source' => 'demo' },
    cached_label_list: t[:labels].join(', ').presence, snoozed_until: nil,
    created_at: t[:updated] - 2.days, updated_at: t[:updated], last_activity_at: t[:updated], status_changed_at: t[:updated],
    agent_last_seen_at: t[:i] % 4 == 1 ? t[:updated] - 1.hour : t[:updated], assignee_last_seen_at: t[:updated],
    contact_last_seen_at: t[:updated] }
end

trigger = 'conversations_before_insert_row_tr'
conn = ActiveRecord::Base.connection
ActiveRecord::Base.transaction do
  conn.execute("ALTER TABLE conversations DISABLE TRIGGER #{trigger}")
  Conversation.upsert_all(conv_rows, unique_by: :index_conversations_on_account_id_and_display_id, record_timestamps: false)
  conn.execute("ALTER TABLE conversations ENABLE TRIGGER #{trigger}")
end
seq = "conv_dpid_seq_#{account.id}"
if conn.select_value("SELECT to_regclass('#{seq}')")
  conn.execute("SELECT setval('#{seq}', GREATEST((SELECT COALESCE(MAX(display_id), 1) FROM conversations WHERE account_id = #{account.id}), " \
               "(SELECT last_value FROM #{seq})))")
end
CONVS = Conversation.where(account_id: account.id, display_id: conv_rows.pluck(:display_id)).index_by(&:display_id)

# etiquetas (acts_as_taggable)
taggings = ticket_plan.flat_map do |t|
  conv = CONVS[DISPLAY_BASE + t[:i] + 1]
  t[:labels].map { |l| { tag_id: TAG_IDS[l], taggable_type: 'Conversation', taggable_id: conv.id, context: 'labels', created_at: NOW } }
end
existing_tags = ActsAsTaggableOn::Tagging.where(taggable_type: 'Conversation', taggable_id: CONVS.values.map(&:id))
                                         .pluck(:tag_id, :taggable_id).to_set
taggings.reject! { |r| existing_tags.include?([r[:tag_id], r[:taggable_id]]) }
ActsAsTaggableOn::Tagging.insert_all(taggings) if taggings.any?

# mensagens (públicas e internas)
CUSTOMER_TEXT = ['Olá, preciso de ajuda com este caso. Seguem os detalhes da reserva de teste.',
                 'Bom dia! O problema continua acontecendo desde ontem.',
                 'Conseguem verificar, por favor? É um dado fictício para teste.'].freeze
AGENT_TEXT = ['Olá! Obrigado pelo contato. Já estamos verificando e retornamos em breve.',
              'Fizemos o ajuste solicitado. Pode confirmar se ficou correto?',
              'Encaminhamos para o time responsável e acompanhamos por aqui.'].freeze
NOTE_TEXT = ['Nota interna: validar com o financeiro antes de responder.',
             'Nota interna: cliente fictício da demo; caso usado para conferir o layout.'].freeze
msg_rows = ticket_plan.flat_map do |t|
  conv = CONVS[DISPLAY_BASE + t[:i] + 1]
  base = t[:updated] - 2.days
  rows = []
  add = lambda do |n, type, private, sender, text|
    rows << { account_id: account.id, inbox_id: conv.inbox_id, conversation_id: conv.id, message_type: type,
              private: private, status: 0, content_type: 0, content: text, processed_message_content: text,
              content_attributes: {}, sender_type: sender&.class&.name, sender_id: sender&.id,
              source_id: "demo:#{conv.display_id}:#{n}", additional_attributes: {}, external_source_ids: {}, sentiment: {},
              created_at: base + (n * 3).hours, updated_at: base + (n * 3).hours }
  end
  add.call(1, 0, false, t[:contact], CUSTOMER_TEXT[t[:i] % 3])
  add.call(2, 1, false, t[:assignee] || AGENTS.first, AGENT_TEXT[t[:i] % 3]) unless t[:native] == 'open' && t[:i].even?
  add.call(3, 1, true, t[:assignee] || AGENTS.first, NOTE_TEXT[t[:i] % 2]) if (t[:i] % 3).zero?
  add.call(4, 0, false, t[:contact], 'Obrigado pelo retorno! (mensagem fictícia)') if t[:native] == 'resolved'
  rows
end
existing_src = Message.where(account_id: account.id, source_id: msg_rows.pluck(:source_id)).pluck(:source_id).to_set
new_msgs = msg_rows.reject { |r| existing_src.include?(r[:source_id]) }
Message.insert_all(new_msgs, record_timestamps: false) if new_msgs.any?
STATS['mensagens_novas'] += new_msgs.size

# ------------------------------------------------------------------ senha do admin (uma vez, 600)
if new_password
  FileUtils.mkdir_p(File.dirname(PASSWORD_FILE))
  File.open(PASSWORD_FILE, File::WRONLY | File::CREAT | File::TRUNC, 0o600) do |f|
    f.puts "ServiceDesk dev (http://localhost:13000 via túnel) - gerado em #{NOW.iso8601}"
    f.puts "conta: #{ACCOUNT_NAME} (id #{account.id})"
    f.puts "usuario: #{ADMIN_EMAIL}"
    f.puts "senha: #{new_password}"
  end
  File.chmod(0o600, PASSWORD_FILE)
  puts "senha do admin gravada em #{PASSWORD_FILE} (600)"
end

# ------------------------------------------------------------------ validação
problems = []
convs = Conversation.where(account_id: account.id, display_id: (DISPLAY_BASE + 1)..(DISPLAY_BASE + 40))
problems << "tickets=#{convs.count} (esperado 40)" if convs.count != 40
problems << "times=#{account.teams.count} (esperado >= 31)" if account.teams.count < 31
missing_status = ACTIVE_STATUSES - convs.pluck(Arel.sql("custom_attributes->>'zd_status'")).compact.uniq
problems << "status sem ticket: #{missing_status}" if missing_status.any?
missing_native = %w[open snoozed resolved] - convs.distinct.pluck(:status)
problems << "status nativo sem ticket: #{missing_native}" if missing_native.any?
missing_prio = %w[low medium high urgent] - convs.distinct.pluck(:priority).compact
problems << "prioridades sem ticket: #{missing_prio}" if missing_prio.any?
missing_forms = (FORMS_META['forms'].select { |_, f| f['active'] }.keys - convs.distinct.pluck(Arel.sql("custom_attributes->>'zd_formulario'")))
problems << "formulários sem ticket: #{missing_forms}" if missing_forms.any?
canon = { 'new' => 'open', 'open' => 'open', 'pending' => 'snoozed', 'hold' => 'snoozed', 'solved' => 'resolved' }
bad_canon = convs.pluck(:display_id, :status, Arel.sql("custom_attributes->>'zd_status'")).select do |_, st, zd|
  zd && (cat = FORMS_META.dig('statuses', zd, 'category')) && canon[cat] != st
end
problems << "status fora do canônico: #{bad_canon.first(5)}" if bad_canon.any?
problems << 'status nativo pending com zd_status' if convs.where(status: :pending).where("custom_attributes->>'zd_status' IS NOT NULL").exists?
zd_names = account.custom_attribute_definitions.where('attribute_display_name ILIKE ?', '%zendesk%').pluck(:attribute_display_name)
problems << "rótulos com Zendesk: #{zd_names}" if zd_names.any?
zd_inboxes = account.inboxes.where('name ILIKE ?', '%zendesk%').pluck(:name)
problems << "inboxes com Zendesk: #{zd_inboxes}" if zd_inboxes.any?
no_org = CONTACTS.count { |c| c.additional_attributes['company_name'].blank? }
problems << 'nenhum contato com company_name' if no_org == CONTACTS.size
problems << 'contato sem identifier zd:' if CONTACTS.any? { |c| !c.identifier.start_with?('zd:') }
problems << 'admin sem acesso de administrador' unless AccountUser.exists?(account: account, user: admin, role: :administrator)
problems << 'e-mail fora de .test' if CONTACTS.any? { |c| !c.email.end_with?('.test') }
dorm = []
dorm << 'IMAP/SMTP habilitado' if Channel::Email.where(account: account).where('imap_enabled OR smtp_enabled').exists?
dorm << 'auto-atribuição' if account.inboxes.exists?(enable_auto_assignment: true) || account.teams.exists?(allow_auto_assign: true)
dorm << 'webhooks' if account.webhooks.exists?
dorm << 'automações ativas' if account.automation_rules.exists?(active: true)
trig = conn.select_value("SELECT tgenabled FROM pg_trigger WHERE tgname = '#{trigger}'")
problems << "trigger #{trigger} desabilitado" unless trig == 'O'

puts STATS.sort.map { |k, v| "#{k}=#{v}" }.join(' ')
puts "conta=#{account.id} times=#{account.teams.count} inboxes=#{account.inboxes.count} " \
     "campos=#{account.custom_attribute_definitions.count} contatos=#{CONTACTS.size} tickets=#{convs.count} " \
     "mensagens=#{Message.where(conversation_id: convs.select(:id)).count} jobs=#{ENQUEUED.size}#{ENQUEUED.any? ? " #{ENQUEUED.tally}" : ''}"
puts dorm.empty? ? 'DORMENCIA_OK' : "DORMENCIA_FALHOU: #{dorm.join(', ')}"
puts problems.empty? ? 'SD_DEMO_OK' : "SD_DEMO_FALHA: #{problems.join('; ')}"
# rubocop:enable Rails/SkipsModelValidations
# rubocop:enable Rails/Output
