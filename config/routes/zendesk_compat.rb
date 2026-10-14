# ServiceDesk (M7): camada de compatibilidade com a API do Zendesk para os workflows do n8n (docs/ZENDESK-COMPAT-API.md).
# Montada em /api/v2/... e /sc/v2/... e também sob "/<subdominio>.zendesk.com/...": com o subdomínio da credencial
# "Zendesk API" do n8n = "<host do ServiceDesk>/<subdominio>", a URL que o n8n monta
# (https://<subdominio>.zendesk.com/api/v2/...) vira https://<host>/<subdominio>.zendesk.com/api/v2/...
# Não colide com /api/v2/accounts/... do Chatwoot. Desligada por padrão (ZENDESK_COMPAT_ENABLED).
# rubocop:disable Metrics/BlockLength
scope '(:zd_host)', constraints: { zd_host: /[a-z0-9][a-z0-9-]*\.zendesk\.com/ }, defaults: { format: 'json' } do
  scope 'api/v2', module: 'zendesk_compat/v2', as: 'zendesk_compat' do
    get 'tickets/show_many', to: 'tickets#show_many'
    get 'tickets/:id', to: 'tickets#show', as: nil
    put 'tickets/:id', to: 'tickets#update', as: nil
    patch 'tickets/:id', to: 'tickets#update', as: nil
    post 'tickets', to: 'tickets#create', as: nil
    get 'tickets/:ticket_id/comments', to: 'ticket_comments#index', as: nil
    get 'tickets/:ticket_id/audits', to: 'ticket_audits#index', as: nil
    get 'tickets/:ticket_id/conversation_log', to: 'conversation_logs#show', as: nil
    get 'tickets/:ticket_id/email_ccs', to: 'ticket_collaborators#email_ccs', as: nil
    get 'tickets/:ticket_id/followers', to: 'ticket_collaborators#followers', as: nil
    get 'tickets/:ticket_id/tags', to: 'ticket_tags#index', as: nil
    post 'tickets/:ticket_id/tags', to: 'ticket_tags#create', as: nil
    put 'tickets/:ticket_id/tags', to: 'ticket_tags#update', as: nil
    delete 'tickets/:ticket_id/tags', to: 'ticket_tags#destroy', as: nil
    get 'users/show_many', to: 'users#show_many', as: nil
    get 'users/search', to: 'users#search', as: nil
    get 'users/me', to: 'users#me', as: nil
    get 'users/:id', to: 'users#show', as: nil
    get 'groups', to: 'groups#index', as: nil
    get 'groups/:id', to: 'groups#show', as: nil
    get 'groups/:group_id/memberships', to: 'groups#memberships', as: nil
    get 'groups/:group_id/users', to: 'groups#users', as: nil
    get 'organizations/show_many', to: 'organizations#show_many', as: nil
    get 'organizations/:id', to: 'organizations#show', as: nil
    get 'search', to: 'search#index', as: nil
    get 'search/count', to: 'search#count', as: nil
    get 'ticket_fields', to: 'ticket_fields#index', as: nil
    get 'ticket_fields/:id', to: 'ticket_fields#show', as: nil
    get 'custom_statuses', to: 'custom_statuses#index', as: nil
    get 'custom_statuses/:id', to: 'custom_statuses#show', as: nil
    post 'uploads', to: 'uploads#create', as: nil
    delete 'uploads/:id', to: 'uploads#destroy', as: nil
    get 'email_notifications', to: 'email_notifications#index', as: nil
    get 'agent_availabilities', to: 'agent_availabilities#index', as: nil
  end

  scope 'sc/v2/apps/:app_id', module: 'zendesk_compat/sunshine', as: nil do
    get 'conversations', to: 'conversations#index'
    get 'conversations/:conversation_id/messages', to: 'messages#index'
    post 'conversations/:conversation_id/messages', to: 'messages#create'
    post 'conversations/:conversation_id/activity', to: 'activities#create'
    post 'attachments', to: 'attachments#create'
  end
end
# rubocop:enable Metrics/BlockLength
