# ServiceDesk B2B: dados FICTÍCIOS para ver o portal do cliente no DEV (docs/PORTAL-CLIENTE.md).
#   bundle exec rails runner db/seeds/servicedesk_portal_demo.rb [nome-da-conta]
# Cria (idempotente): inbox API "Central de Ajuda", portal "central-b2b" com o tema B2B, as categorias e seções
# da Central do Zendesk (só os nomes), artigos de exemplo (públicos e restritos), segmentos, uma empresa,
# dois contatos e tickets com status variados. Nada aqui vem de dados reais de clientes.
account = Account.find_by(name: ARGV[0].presence || 'ServiceDesk Demo') || Account.first
admin = account.administrators.first || account.users.first
raise 'conta sem usuários' unless admin

inbox = account.inboxes.find_by(name: 'Central de Ajuda') ||
        account.inboxes.create!(name: 'Central de Ajuda', channel: Channel::Api.create!(account: account))

portal = account.portals.find_or_initialize_by(slug: 'central-b2b')
portal.assign_attributes(
  name: 'Central de Ajuda B2B.reservas', page_title: 'Central de Ajuda B2B.reservas', color: '#3E54C0',
  homepage_link: 'https://b2breservas.com.br', header_text: 'Pesquise os artigos ou navegue pelas categorias abaixo.',
  config: {
    'allowed_locales' => ['pt_BR'], 'default_locale' => 'pt_BR',
    'customer_portal' => { 'enabled' => true, 'require_sign_in' => true, 'theme' => 'b2b',
                           'organization_requests' => true, 'request_inbox_id' => inbox.id }
  }
)
portal.save!

signed_in = PortalUserSegment.find_or_create_by!(portal: portal, external_id: '21136425681947') do |s|
  s.account = account
  s.name = 'Usuários conectados'
end
PortalUserSegment.find_or_create_by!(portal: portal, external_id: '21136404041499') do |s|
  s.account = account
  s.name = 'Agentes e administradores'
  s.user_type = :staff
end

# Estrutura da Central do Zendesk da B2B (categorias com a descrição de lá e as seções), com artigos fictícios
structure = {
  'B2B.hospitality' => ['Gestão da operação hoteleira: disponibilidade, tarifas, flutuação, reservas, políticas e formas de pagamento.',
                        %w[Reservas Tarifas Quartos Calendário Políticas Clientes]],
  'B2B.checkout' => ['Cobrança e conciliação: links de pagamento, transações, extratos e financeiro.',
                     ['Cobrança de Reservas', 'Link de Pagamento', 'Financeiro', 'Incentivos e Comissões']],
  'B2B.booking' => ['Consulta e gestão de reservas, administração de políticas de venda e configurações do Booking.',
                    ['Booking', 'Booking - Administração']],
  'B2B.pay' => ['Conciliação eletrônica, relatório financeiro, cadastro de cobranças e emissão de VCN.',
                ['Emissão de VCN', 'Relatórios', 'Usuários', 'Administração']],
  'Perguntas Frequentes - FAQ' => ['Dúvidas frequentes sobre acesso, reservas, pagamentos e regras de uso das plataformas B2B.',
                                   %w[Hospitality Checkout Financeiro Integrações Usuários]],
  'Vídeos' => ['Tutoriais em vídeo com o passo a passo das principais funcionalidades.', ['B2B.hospitality']]
}
structure.each_with_index do |(cat_name, (description, sections)), position|
  category = portal.categories.find_or_initialize_by(slug: "demo-#{cat_name.parameterize}", locale: 'pt_BR')
  category.update!(account_id: account.id, name: cat_name, description: description, position: position)
  sections.each_with_index do |section_name, section_position|
    section = portal.categories.find_or_initialize_by(slug: "demo-#{cat_name.parameterize}-#{section_name.parameterize}", locale: 'pt_BR')
    section.update!(account_id: account.id, name: section_name, position: section_position, parent_category_id: category.id)
    (section_position < 3 ? 3 : 1).times do |index|
      article = portal.articles.find_or_initialize_by(slug: "demo-#{cat_name.parameterize}-#{section_name.parameterize}-#{index + 1}")
      article.assign_attributes(
        account_id: account.id, author: admin, category: section, locale: 'pt_BR', status: :published, position: index,
        title: ["Como configurar #{section_name}", "Perguntas sobre #{section_name}", "Passo a passo: #{section_name} no #{cat_name}"][index],
        description: "Artigo fictício de demonstração sobre #{section_name}.",
        content: "Artigo **fictício** para demonstrar a Central de Ajuda.\n\n## Passo a passo\n\n1. Acesse o painel.\n" \
                 "2. Abra o menu *#{section_name}*.\n3. Salve as alterações.\n\n> Dúvidas? Use **Enviar uma solicitação**.",
        portal_user_segment: index.zero? && section_position.zero? ? nil : signed_in
      )
      article.save!
    end
  end
end
# remove os artigos da versão anterior desta seed (sem seção)
portal.articles.where(category_id: portal.categories.where(parent_category_id: nil).select(:id)).where("slug LIKE 'demo-%'").destroy_all

company = Company.find_or_create_by!(account: account, name: 'Hotel Exemplo (fictício)') do |c|
  c.custom_attributes = { 'portal_shared_requests' => true }
end
company_id = company.id

mariana = account.contacts.find_or_create_by!(email: 'mariana.teste@exemplo.com.br') { |c| c.name = 'Mariana Teste' }
joao = account.contacts.find_or_create_by!(email: 'joao.teste@exemplo.com.br') { |c| c.name = 'João Teste' }
[mariana, joao].each { |c| c.update_columns(company_id: company_id.to_i) } # rubocop:disable Rails/SkipsModelValidations

tickets = [
  [mariana, 'Tarifa de fim de semana não aparece no motor', :open, 'Em andamento',
   ['Configurei a tarifa de sábado e domingo, mas ela não aparece no motor de reservas.',
    'Olá, Mariana! Estamos verificando a configuração da sua tarifa e retornamos em breve.']],
  [mariana, 'Segunda via do boleto de outubro', :waiting_on_customer, 'Pendente',
   ['Preciso da segunda via do boleto de outubro.', 'Enviamos a segunda via. Pode confirmar se recebeu?']],
  [mariana, 'Erro ao conectar o channel manager', :on_hold, 'Desenvolvimento',
   ['A conexão com o channel manager retorna erro desde ontem.',
    'Encaminhamos para o time de desenvolvimento. Avisaremos quando estiver corrigido.']],
  [mariana, 'Como cadastrar um novo usuário no B2B.pay', :resolved, 'Resolvido',
   ['Como cadastro um novo usuário no B2B.pay?', 'Basta acessar Usuários > Novo usuário. Qualquer dúvida, estamos à disposição.']],
  [joao, 'Ajuste de política de cancelamento', :open, 'Aberto', ['Gostaria de alterar a política de cancelamento do hotel.']]
]
tickets.each do |contact, subject, status, zd_status, messages|
  next if account.conversations.where(contact_id: contact.id).exists?(["additional_attributes->>'mail_subject' = ?", subject])

  contact_inbox = ContactInboxBuilder.new(contact: contact, inbox: inbox).perform
  conversation = Conversation.create!(
    account: account, inbox: inbox, contact: contact, contact_inbox: contact_inbox,
    subject: subject, additional_attributes: { 'mail_subject' => subject, 'source' => 'help_center' },
    custom_attributes: { 'zd_assunto' => subject, 'zd_formulario' => 'Atendimento', 'zd_canal' => 'Central de Ajuda',
                         'zd_status' => zd_status, 'zd_cnpj_o_cuit_argentina' => '00.000.000/0001-00' }
  )
  messages.each_with_index do |content, index|
    conversation.messages.create!(account: account, inbox: inbox, content: content,
                                  message_type: index.even? ? :incoming : :outgoing, sender: index.even? ? contact : admin)
  end
  conversation.messages.create!(account: account, inbox: inbox, content: 'Nota interna (não aparece no portal).',
                                message_type: :outgoing, private: true, sender: admin)
  conversation.update!(status: status, assignee: admin)
  conversation.update_columns(custom_attributes: conversation.custom_attributes.merge('zd_status' => zd_status)) # rubocop:disable Rails/SkipsModelValidations
end

# rubocop:disable Rails/Output
puts "portal=/hc/#{portal.slug}/pt_BR inbox=#{inbox.id} artigos=#{portal.articles.count} " \
     "restritos=#{portal.articles.where.not(portal_user_segment_id: nil).count} " \
     "tickets_mariana=#{account.conversations.where(contact_id: mariana.id).count} contato=#{mariana.email}"
# rubocop:enable Rails/Output
