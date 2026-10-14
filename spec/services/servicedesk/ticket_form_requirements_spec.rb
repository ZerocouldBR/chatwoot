require 'rails_helper'

RSpec.describe Servicedesk::TicketFormRequirements do
  let(:account) { create(:account) }
  let(:inbox) { create(:inbox, account: account) }

  def define_field(key, field_id, name, values = [])
    create(:custom_attribute_definition, account: account, attribute_model: :conversation_attribute,
                                         attribute_key: key, attribute_display_name: name,
                                         attribute_display_type: values.any? ? :list : :text,
                                         attribute_values: values, attribute_description: "zendesk_field:#{field_id}")
  end

  def missing_keys(attrs)
    conversation = create(:conversation, account: account, inbox: inbox, custom_attributes: attrs)
    described_class.new(conversation).missing.pluck(:key)
  end

  before do
    define_field('zd_area_interna', 21_587_135_564_955, 'Área interna', %w[Suporte Checkout Hospitality])
    define_field('zd_checkout', 27_073_292_749_723, 'Checkout')
    define_field('zd_hospitality', 21_538_028_391_067, 'Hospitality')
    define_field('zd_tabulacao', 21_537_600_796_443, 'Tabulação')
    define_field('zd_motivo_lgpd', 23_735_231_881_243, 'Motivo LGPD')
  end

  it 'uses the default form when the ticket has none and requires Área interna' do
    expect(missing_keys({})).to eq(['zd_area_interna'])
  end

  it 'requires the child field of a met condition and ignores unmet conditional fields' do
    expect(missing_keys('zd_area_interna' => 'Hospitality')).to eq(['zd_hospitality'])
    expect(missing_keys('zd_area_interna' => 'Checkout')).to eq(['zd_checkout'])
    expect(missing_keys('zd_area_interna' => 'Suporte')).to eq([])
  end

  it 'reports nothing when the required fields are filled' do
    expect(missing_keys('zd_area_interna' => 'Hospitality', 'zd_hospitality' => 'Sim')).to eq([])
  end

  it 'follows the form of the ticket' do
    expect(missing_keys('zd_formulario' => 'LGPD & Segurança')).to eq(['zd_motivo_lgpd'])
  end

  it 'falls back to the default form for an unknown form name' do
    conversation = create(:conversation, account: account, inbox: inbox, custom_attributes: { 'zd_formulario' => 'Outro' })
    expect(described_class.new(conversation).form_name).to eq('Atendimento')
  end

  it 'does not require an inactive field' do
    CustomAttributeDefinition.find_by(attribute_key: 'zd_area_interna').update!(attribute_display_name: 'Área interna (inativo)')
    expect(missing_keys({})).to eq([])
  end

  it 'requires nothing when the account has no form fields' do
    other = create(:account)
    conversation = create(:conversation, account: other, inbox: create(:inbox, account: other))
    expect(described_class.new(conversation).missing).to eq([])
  end
end
