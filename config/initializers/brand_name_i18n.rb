# Translations ship with the upstream product name baked in. Swap it for the
# installation name in the translation templates (before interpolation, so
# dynamic values such as URLs or customer content are never rewritten).
module BrandNameTranslation
  BRAND_PATTERN = /chatwoot/i
  DEFAULT_BRAND_NAME = 'Helpdesk'.freeze

  protected

  def lookup(locale, key, scope = [], options = I18n::EMPTY_HASH)
    replace_brand_name(super)
  end

  private

  def replace_brand_name(value)
    case value
    when String
      value.match?(BRAND_PATTERN) ? value.gsub(BRAND_PATTERN, brand_name) : value
    when Hash
      value.transform_values { |v| replace_brand_name(v) }
    when Array
      value.map { |v| replace_brand_name(v) }
    else
      value
    end
  end

  def brand_name
    GlobalConfig.get_value('INSTALLATION_NAME').presence || DEFAULT_BRAND_NAME
  rescue StandardError
    DEFAULT_BRAND_NAME
  end
end

I18n::Backend::Simple.prepend(BrandNameTranslation)
