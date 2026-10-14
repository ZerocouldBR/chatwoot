# ServiceDesk M13: uma macro só pode ser aplicada se todas as ações cabem no papel de quem aplica.
#   - add_private_note: sempre (nota interna é o que o agente light faz);
#   - send_message / send_attachment: exigem ticket.comment_public, exceto quando a conta preenche o editor
#     (macro_fill_editor, M5.1): aí o texto vai para o editor e o envio passa pelo POST de mensagem, que já é
#     barrado para quem só pode nota interna;
#   - add_label / remove_label: ticket.edit_tags;
#   - send_email_transcript / send_webhook_event: ticket.comment_public / ticket.edit;
#   - todas as demais (status, prioridade, responsável, time, campos, assunto, silenciar...): ticket.edit.
class Servicedesk::Roles::MacroGuard
  NOTE_ACTIONS = %w[add_private_note].freeze
  REPLY_ACTIONS = %w[send_message send_attachment].freeze
  TAG_ACTIONS = %w[add_label remove_label].freeze
  PUBLIC_ACTIONS = %w[send_email_transcript].freeze

  def initialize(macro, access)
    @macro = macro
    @access = access
  end

  def allowed?
    return true if @access.administrator?

    denied_actions.empty?
  end

  def denied_actions
    Array(@macro.actions).map { |action| action.with_indifferent_access[:action_name].to_s }.uniq.reject { |name| action_allowed?(name) }
  end

  private

  def action_allowed?(name)
    return true if NOTE_ACTIONS.include?(name)
    return @access.can?('ticket.comment_public') || fill_editor? if REPLY_ACTIONS.include?(name)
    return @access.can?('ticket.edit_tags') if TAG_ACTIONS.include?(name)
    return @access.can?('ticket.comment_public') if PUBLIC_ACTIONS.include?(name)

    @access.can?('ticket.edit')
  end

  # macro_fill_editor (M5.1) só existe quando as configurações de macro do ServiceDesk estão na conta
  def fill_editor?
    account = @macro.account
    account.respond_to?(:macro_fill_editor?) && account.macro_fill_editor?
  end
end
