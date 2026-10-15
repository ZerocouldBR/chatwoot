require 'rails_helper'

RSpec.describe BrandNameTranslation do
  before do
    I18n.backend.store_translations(:en, brand_spec: { greeting: 'Welcome to Chatwoot', link: 'Open %{url}' }) # rubocop:disable Style/FormatStringToken
    allow(GlobalConfig).to receive(:get_value).and_call_original
    allow(GlobalConfig).to receive(:get_value).with('INSTALLATION_NAME').and_return('Acme Desk')
  end

  it 'replaces the upstream name with the installation name' do
    expect(I18n.t('brand_spec.greeting')).to eq('Welcome to Acme Desk')
  end

  it 'leaves interpolated values untouched' do
    expect(I18n.t('brand_spec.link', url: 'https://chatwoot.example.com')).to eq('Open https://chatwoot.example.com')
  end

  it 'falls back to a neutral name when none is configured' do
    allow(GlobalConfig).to receive(:get_value).with('INSTALLATION_NAME').and_return(nil)
    expect(I18n.t('brand_spec.greeting')).to eq('Welcome to ServiceDesk')
  end

  it 'keeps domains and interpolation keys intact' do
    I18n.backend.store_translations(:en, brand_spec: { terms: 'Chatwoot terms: https://www.chatwoot.com/terms (%{chatwoot_url})' }) # rubocop:disable Style/FormatStringToken
    expect(I18n.t('brand_spec.terms', chatwoot_url: 'x')).to eq('Acme Desk terms: https://www.chatwoot.com/terms (x)')
  end
end
