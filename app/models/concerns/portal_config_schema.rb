module PortalConfigSchema
  extend ActiveSupport::Concern

  # Per-locale overrides for portal level fields. Any locale present in
  # `allowed_locales` may carry its own `name`, `page_title` and `header_text`.
  # Missing values fall back to the default locale and finally to the base column.
  LOCALE_TRANSLATION_SCHEMA = {
    'type' => 'object',
    'properties' => {
      'name' => { 'type' => %w[string null] },
      'page_title' => { 'type' => %w[string null] },
      'header_text' => { 'type' => %w[string null] }
    },
    'additionalProperties' => false
  }.freeze

  # Per-locale recommended content for the portal home page: an ordered list of
  # `category_ids` (the hero's "Recommended topics" pills) and `article_ids` (the
  # "Recommended" articles section). When empty, the portal uses its defaults.
  POPULAR_CONTENT_SCHEMA = {
    'type' => 'object',
    'properties' => {
      'category_ids' => { 'type' => %w[array null], 'items' => { 'type' => 'integer' } },
      'article_ids' => { 'type' => %w[array null], 'items' => { 'type' => 'integer' } }
    },
    'additionalProperties' => false
  }.freeze

  # ServiceDesk B2B: configuração do portal do cliente (login, solicitações e tema).
  REQUEST_FORM_FIELD_SCHEMA = {
    'type' => 'object',
    'properties' => {
      'key' => { 'type' => 'string' },
      'label' => { 'type' => 'string' },
      'type' => { 'type' => 'string', 'enum' => %w[text textarea list number] },
      'required' => { 'type' => %w[boolean null] },
      'description' => { 'type' => %w[string null] },
      'attribute_key' => { 'type' => %w[string null] },
      'options' => { 'type' => %w[array null], 'items' => { 'type' => 'string' } }
    },
    'required' => %w[key label type]
  }.freeze

  REQUEST_FORM_SCHEMA = {
    'type' => 'object',
    'properties' => {
      'id' => { 'type' => 'string' },
      'name' => { 'type' => 'string' },
      'description' => { 'type' => %w[string null] },
      'inbox_id' => { 'type' => %w[integer null] },
      'zendesk_id' => { 'type' => %w[integer string null] },
      'fields' => { 'type' => %w[array null], 'items' => REQUEST_FORM_FIELD_SCHEMA }
    },
    'required' => %w[id name]
  }.freeze

  CUSTOMER_PORTAL_SCHEMA = {
    'type' => %w[object null],
    'properties' => {
      'enabled' => { 'type' => %w[boolean null] },
      'require_sign_in' => { 'type' => %w[boolean null] },
      'organization_requests' => { 'type' => %w[boolean null] },
      'theme' => { 'type' => %w[string null] },
      'sso_login_url' => { 'type' => %w[string null] },
      'request_inbox_id' => { 'type' => %w[integer null] },
      'request_forms' => { 'type' => %w[array null], 'items' => REQUEST_FORM_SCHEMA },
      'footer_links' => {
        'type' => %w[array null],
        'items' => { 'type' => 'object', 'properties' => { 'label' => { 'type' => 'string' }, 'url' => { 'type' => 'string' } } }
      }
    }
  }.freeze

  CONFIG_PARAMS_SCHEMA = {
    'type' => 'object',
    'properties' => {
      'allowed_locales' => { 'type' => %w[array null], 'items' => { 'type' => 'string' } },
      'default_locale' => { 'type' => %w[string null] },
      'draft_locales' => { 'type' => %w[array null], 'items' => { 'type' => 'string' } },
      'layout' => { 'type' => %w[string null], 'enum' => ['classic', 'documentation', nil] },
      # TODO: unused reserved key; remove with a migration that scrubs it from existing portals' config
      'website_token' => { 'type' => %w[string null] },
      'social_profiles' => { 'type' => %w[object null] },
      'locale_translations' => {
        'type' => %w[object null],
        'additionalProperties' => LOCALE_TRANSLATION_SCHEMA
      },
      'popular_content' => {
        'type' => %w[object null],
        'additionalProperties' => POPULAR_CONTENT_SCHEMA
      },
      'customer_portal' => CUSTOMER_PORTAL_SCHEMA,
      # Analytics ids grouped under one object (see Portal::ANALYTICS_CONFIG_FORMATS).
      'analytics' => {
        'type' => %w[object null],
        'properties' => {
          'gtm_container_id' => { 'type' => %w[string null] },
          'ga4_measurement_id' => { 'type' => %w[string null] },
          'hotjar_site_id' => { 'type' => %w[string null] },
          'plausible_domain' => { 'type' => %w[string null] },
          'amplitude_api_key' => { 'type' => %w[string null] },
          'clarity_project_id' => { 'type' => %w[string null] },
          'meta_pixel_id' => { 'type' => %w[string null] }
        },
        'additionalProperties' => false
      }
    },
    'required' => [],
    'additionalProperties' => true
  }.to_json.freeze
end
