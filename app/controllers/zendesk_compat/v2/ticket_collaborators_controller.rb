# GET /api/v2/tickets/:ticket_id/email_ccs(.json) e /followers(.json): usuários em CC (ZendeskCompat::TicketModel) e seguidores
# (participantes da conversa), no formato {users: [...]} do Zendesk.
class ZendeskCompat::V2::TicketCollaboratorsController < ZendeskCompat::BaseController
  def email_ccs
    conversation = find_ticket!
    emails = ZendeskCompat::TicketModel.cc_emails(conversation)
    records = emails.map { |email| context.directory.actor_by_email(email) || placeholder(email) }
    render json: { users: records.map { |record| present(record) } }
  end

  def followers
    users = find_ticket!.conversation_participants.includes(:user).filter_map(&:user)
    render json: { users: users.map { |user| present(user) } }
  end

  private

  # E-mail em CC sem contato cadastrado: devolve um usuário final mínimo (id nulo), para o workflow ver o endereço.
  def placeholder(email)
    Contact.new(email: email, name: email.split('@').first, account: current_account, created_at: Time.current, updated_at: Time.current)
  end

  def present(record)
    @presenter ||= ZendeskCompat::UserPresenter.new(context)
    @presenter.present(record)
  end
end
