# rubocop:disable RSpec/DescribeClass
require 'rails_helper'

RSpec.describe 'ZendeskCompat: tradução de status, campos, ids e tags' do
  let(:account) { create(:account) }

  describe ZendeskCompat::StatusTranslator do
    def snapshot(status, label = nil, system = nil)
      Servicedesk::TicketAuditEvents::Snapshot.new(status, { 'zd_status' => label, 'zd_status_sistema' => system }.compact)
    end

    it 'lê a categoria pelo rótulo, closed pelo status do sistema e cai no nativo sem rótulo' do
      expect(described_class.category(snapshot('open', 'Novo'))).to eq('new')
      expect(described_class.category(snapshot('snoozed', 'Desenvolvimento'))).to eq('hold')
      expect(described_class.category(snapshot('resolved', 'Concluído'))).to eq('solved')
      expect(described_class.category(snapshot('resolved', 'Resolvido', 'Fechado'))).to eq('closed')
      expect(described_class.category(snapshot('snoozed'))).to eq('pending')
      expect(described_class.category(snapshot('pending'))).to eq('new')
    end

    it 'traduz status e custom_status_id do Zendesk para rótulo + status nativo' do
      expect(described_class.attributes_for(status: 'pending')).to include(native: 'snoozed', label: 'Pendente')
      expect(described_class.attributes_for(status: 'solved')).to include(native: 'resolved', label: 'Resolvido')
      expect(described_class.attributes_for(status: 'hold')).to include(native: 'snoozed', label: 'Desenvolvimento')
      expect(described_class.attributes_for(status: 'closed')).to include(native: 'resolved', system_label: 'Fechado')
      expect(described_class.attributes_for(custom_status_id: 23_819_380_599_963)).to include(native: 'resolved', label: 'Respondido cliente')
      expect(described_class.attributes_for(status: 'bogus')).to be_nil
      expect(described_class.attributes_for(custom_status_id: 1)).to be_nil
    end
  end

  describe ZendeskCompat::FieldTranslator do
    let(:translator) { described_class.new(account) }
    let(:tabulacao) { ZendeskCompat::Config.ticket_field(21_537_600_796_443) }

    it 'converte tag <-> nome da opção e ignora campos de sistema e ids desconhecidos' do
      attrs = translator.attributes_from([{ 'id' => 21_537_600_796_443, 'value' => 'cancelamento_interno' },
                                          { 'id' => 20_487_430_449_819, 'value' => 'assunto' }, { 'id' => 1, 'value' => 'x' }])
      expect(attrs).to eq('zd_tabulacao' => 'Cancelamento Interno')
      expect(translator.zendesk_value(tabulacao, 'Cancelamento Interno')).to eq('cancelamento_interno')
      expect(translator.attributes_from({ '21537600796443' => nil })).to eq('zd_tabulacao' => nil)
    end

    it 'usa a definição do atributo da conta (zendesk_field:<id>) antes da chave do mapa' do
      create(:custom_attribute_definition, account: account, attribute_model: 'conversation_attribute', attribute_key: 'tabulacao_nova',
                                           attribute_description: 'zendesk_field:21537600796443')
      expect(translator.attribute_key(tabulacao)).to eq('tabulacao_nova')
    end
  end

  describe ZendeskCompat::Ids do
    it 'usa o id de origem e as faixas para registros sem id do Zendesk' do
      user = create(:user, custom_attributes: { 'zendesk_user_id' => '36212918767515' })
      plain = create(:user)
      contact = create(:contact, account: account, identifier: 'zd:24033324330395')
      new_contact = create(:contact, account: account)
      bot = create(:agent_bot, bot_config: { 'zendesk_user_id' => '40000000000001' })
      expect(described_class.user_id(user)).to eq(36_212_918_767_515)
      expect(described_class.user_id(plain)).to eq(described_class::USER_BASE + plain.id)
      expect(described_class.user_id(contact)).to eq(24_033_324_330_395)
      expect(described_class.user_id(new_contact)).to eq(new_contact.id)
      expect(described_class.user_id(bot)).to eq(40_000_000_000_001)
    end

    it 'resolve de volta pelo Directory só dentro da conta' do
      contact = create(:contact, account: account, identifier: 'zd:24033324330395')
      create(:contact, account: create(:account), identifier: 'zd:99')
      directory = ZendeskCompat::Directory.new(account)
      expect(directory.actor(24_033_324_330_395)).to eq(contact)
      expect(directory.actor(99)).to be_nil
      expect(directory.actor(contact.id)).to eq(contact)
    end
  end

  describe ZendeskCompat::Tags do
    it 'normaliza como a importação' do
      expect(described_class.normalize(['Excluído/Spam', '-abc', 'x', 'no_ai', 'no_ai'])).to eq(%w[excluído_spam abc tag_x no_ai])
      expect(described_class.normalize('a1 b2')).to eq(%w[a1 b2])
    end
  end

  describe ZendeskCompat::Authenticator do
    def request_with(headers)
      ActionDispatch::Request.new(Rack::MockRequest.env_for('/api/v2/tickets/1.json', headers.transform_keys { |k| "HTTP_#{k.upcase.tr('-', '_')}" }))
    end

    it 'aceita email/token:token, id:token, Bearer e api_access_token; recusa e-mail divergente' do
      user = create(:user, account: account, role: :administrator)
      token = user.access_token.token
      basic = ->(login) { "Basic #{Base64.strict_encode64("#{login}:#{token}")}" }
      expect(described_class.new(request_with('Authorization' => basic.call("#{user.email}/token"))).user).to eq(user)
      expect(described_class.new(request_with('Authorization' => basic.call('app_123'))).user).to eq(user)
      expect(described_class.new(request_with('Authorization' => "Bearer #{token}")).user).to eq(user)
      expect(described_class.new(request_with('api_access_token' => token)).user).to eq(user)
      expect(described_class.new(request_with('Authorization' => basic.call('outro@example.com/token'))).user).to be_nil
    end
  end

  describe ZendeskCompat::SearchQuery do
    it 'recusa termos fora do subconjunto suportado' do
      context = ZendeskCompat::Context.new(account: account, user: create(:user), api_base: 'http://x/api/v2')
      expect { described_class.new(context, 'fieldvalue:abc') }.to raise_error(ZendeskCompat::Error::Unsupported)
      expect { described_class.new(context, 'updated>ontem') }.to raise_error(ZendeskCompat::Error)
    end
  end
end
# rubocop:enable RSpec/DescribeClass
