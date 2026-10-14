# ServiceDesk M13: matriz de enforcement dos papéis nos endpoints da API de conta (um lugar só, auditável).
#
# Cada linha: controller_path => { action => regra }. A regra é um predicado do ConversationPolicy (verificado
# com Pundit sobre a classe Conversation, porque depende só do papel) ou um método próprio para as regras que
# olham os parâmetros (resposta pública, atribuição, ações em massa). Administradores e AgentBots passam direto.
# A visibilidade (quais tickets o usuário vê) fica no PermissionFilterService/ConversationPolicy#show?.
module Servicedesk::RoleEnforcement
  extend ActiveSupport::Concern

  RULES = {
    'api/v1/accounts/conversations' => {
      'create' => :reply_public?,          # abrir conversa com o cliente envia mensagem pública
      'transcript' => :reply_public?,      # envia a conversa por e-mail
      'update' => :edit_ticket?,
      'toggle_status' => :edit_ticket?,
      'toggle_priority' => :edit_ticket?,
      'custom_attributes' => :edit_ticket?,
      'destroy_custom_attributes' => :edit_ticket?
    },
    'api/v1/accounts/conversations/messages' => {
      'create' => :sd_check_message_create,
      'destroy' => :redact_message?
    },
    'api/v1/accounts/conversations/assignments' => { 'create' => :sd_check_assignment },
    # Módulos do Victor (f3..f8): mesclar, spam, redação, CCs e lixeira, conforme o papel
    'api/v1/accounts/conversations/merges' => { 'create' => :merge_ticket? },
    'api/v1/accounts/conversations/spams' => { 'create' => :delete_ticket? },
    'api/v1/accounts/conversations/redactions' => { 'create' => :redact_message? },
    'api/v1/accounts/conversations/ccs' => { 'create' => :edit_ticket?, 'destroy' => :edit_ticket? },
    'api/v1/accounts/deleted_tickets' => { 'index' => :view_deleted?, 'restore' => :view_deleted?, 'destroy' => :delete_ticket? },
    'api/v1/accounts/conversations/labels' => { 'create' => :edit_tags? },
    'api/v1/accounts/conversations/contact_info_requests' => { 'create' => :reply_public? },
    'api/v1/accounts/bulk_actions' => { 'create' => :sd_check_bulk_action },
    'api/v1/accounts/macros' => { 'create' => :sd_check_macro_create }, # o controller nativo não autoriza o create
    'api/v1/accounts/contacts/labels' => { 'create' => :sd_check_contacts_edit },
    'api/v1/accounts/contacts/notes' => { 'create' => :sd_check_contacts_edit, 'update' => :sd_check_contacts_edit,
                                          'destroy' => :sd_check_contacts_edit }
  }.freeze

  # Negado pelo papel: 403 com a mensagem (o 401 genérico do Pundit faria o painel tratar como sessão inválida).
  class Denied < StandardError; end

  included do
    before_action :sd_enforce_role!, if: :sd_role_enforced?
  end

  private

  # Administrador também passa pela matriz: as permissões dele são todas liberadas, mas a regra do responsável
  # (agente light/colaborador/suspenso não pode ser responsável) vale para todos, como no Zendesk.
  def sd_role_enforced?
    Current.user.is_a?(User) && Current.account_user.present? && RULES.key?(controller_path)
  end

  def sd_access
    Servicedesk::Roles::Access.for(Current.account_user)
  end

  def sd_enforce_role!
    rule = RULES.dig(controller_path, action_name)
    return if rule.nil?

    if rule.to_s.start_with?('sd_check_')
      send(rule)
    else
      sd_forbid!('ServiceDesk: seu papel não permite esta ação') unless ConversationPolicy.new(pundit_user, Conversation).public_send(rule)
    end
  rescue Denied => e
    render json: { error: e.message, servicedesk_role: true }, status: :forbidden
  end

  def sd_forbid!(reason)
    raise Denied, reason
  end

  # Resposta pública só com ticket.comment_public; quem não tem só grava nota interna (private=true).
  def sd_check_message_create
    is_private = ActiveModel::Type::Boolean.new.cast(params[:private]) == true
    return if is_private || sd_access.can?('ticket.comment_public')

    sd_forbid!('ServiceDesk: seu papel só permite nota interna')
  end

  # Atribuir exige ticket.edit; o responsável precisa poder ser atribuído; o time precisa ser um dos do agente
  # quando o papel não tem ticket.assign_any_team.
  def sd_check_assignment
    sd_forbid!('ServiceDesk: seu papel não permite editar o ticket') unless sd_access.can?('ticket.edit')
    sd_check_assignee!(params[:assignee_id]) if params.key?(:assignee_id) && params[:assignee_type].to_s != 'AgentBot'
    sd_check_team!(params[:team_id]) if params.key?(:team_id) && !params.key?(:assignee_id)
  end

  def sd_check_bulk_action
    return unless params[:type].to_s.camelize == 'Conversation'

    sd_check_bulk_labels
    fields = params[:fields]
    return if fields.blank?

    sd_forbid!('ServiceDesk: seu papel não permite editar o ticket') unless sd_access.can?('ticket.edit')
    sd_check_assignee!(fields[:assignee_id]) if fields.key?(:assignee_id)
    sd_check_team!(fields[:team_id]) if fields.key?(:team_id)
  end

  def sd_check_bulk_labels
    return if params[:labels].blank? || sd_access.can?('ticket.edit_tags')

    sd_forbid!('ServiceDesk: seu papel não permite editar etiquetas')
  end

  def sd_check_macro_create
    sd_forbid!('ServiceDesk: seu papel só permite usar macros') unless sd_access.can?('macros')
  end

  def sd_check_contacts_edit
    sd_forbid!('ServiceDesk: seu papel só permite ver o usuário final') unless sd_access.can?('contacts.edit')
  end

  def sd_check_assignee!(assignee_id)
    return if assignee_id.blank? || assignee_id.to_s == '0'

    target = Current.account.account_users.includes(:sd_role).find_by(user_id: assignee_id)
    return if target.nil? # o controller nativo já responde para usuário inexistente
    return if target.sd_assignable?

    sd_forbid!('ServiceDesk: este agente não pode ser responsável por tickets')
  end

  def sd_check_team!(team_id)
    return if team_id.blank? || team_id.to_s == '0' || sd_access.can?('ticket.assign_any_team')
    return if Current.user.teams.where(account_id: Current.account.id).exists?(id: team_id)

    sd_forbid!('ServiceDesk: seu papel só permite atribuir aos seus grupos')
  end
end
