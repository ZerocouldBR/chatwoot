# Usuário no formato do Zendesk: agente (User), bot (AgentBot) ou usuário final (Contact).
# role: 'admin' (administrador da conta), 'agent' (agente, bot ou autor sem acesso) e 'end-user' (contato).
class ZendeskCompat::UserPresenter
  def initialize(context)
    @context = context
  end

  def present(record)
    case record
    when User then agent(record)
    when AgentBot then bot(record)
    when Contact then end_user(record)
    end
  end

  private

  def base(record, id)
    {
      id: id, url: @context.api_url("users/#{id}.json"), name: record.name.to_s, created_at: @context.time(record.created_at),
      updated_at: @context.time(record.updated_at), time_zone: 'Brasilia', iana_time_zone: 'America/Sao_Paulo', locale: 'pt-BR',
      locale_id: 19, photo: nil, verified: true, active: true, shared: false, shared_agent: false, two_factor_auth_enabled: false,
      ticket_restriction: nil, restricted_agent: false, only_private_comments: false, moderator: false, report_csv: false,
      alias: nil, signature: nil, details: '', notes: '', external_id: nil, tags: [], user_fields: {},
      organization_id: nil, default_group_id: nil, custom_role_id: nil, role_type: nil, last_login_at: nil, shared_phone_number: nil
    }
  end

  def agent(user)
    account_user = @context.account_user(user)
    base(user, ZendeskCompat::Ids.user_id(user)).merge(
      email: user.email, phone: nil, role: account_user&.administrator? ? 'admin' : 'agent',
      role_type: account_user&.administrator? ? nil : 0, moderator: true, alias: user.display_name,
      signature: user.message_signature, suspended: user.custom_attributes&.dig('suspended_at').present?,
      active: account_user.present?, last_login_at: @context.time(user.last_sign_in_at),
      default_group_id: default_group_id(user), custom_role_id: account_user&.custom_role_id
    )
  end

  def bot(agent_bot)
    base(agent_bot, ZendeskCompat::Ids.user_id(agent_bot)).merge(email: nil, phone: nil, role: 'agent', suspended: false,
                                                                 details: agent_bot.description.to_s)
  end

  def end_user(contact)
    additional = contact.additional_attributes || {}
    zendesk = additional['zendesk'] || {}
    base(contact, ZendeskCompat::Ids.contact_id(contact)).merge(
      email: contact.email, phone: contact.phone_number.presence || zendesk['phone'], role: 'end-user', suspended: contact.blocked,
      organization_id: ZendeskCompat::Ids.organization_id(@context.company(contact)) || zendesk['organization_id'],
      notes: additional['description'].to_s, details: zendesk['details'].to_s, external_id: zendesk['external_id'],
      tags: Array(zendesk['tags']), user_fields: user_fields(contact)
    )
  end

  def default_group_id(user)
    team = user.teams.where(account_id: @context.account.id).first if user.respond_to?(:teams)
    team && @context.directory.group_id(team)
  end

  def user_fields(contact)
    attributes = contact.custom_attributes || {}
    ZendeskCompat::Config.user_fields.to_h do |field|
      value = attributes[field['attr']]
      value = ZendeskCompat::Config.option_tag(field, value) if field['type'] == 'list' && value.present?
      value = value.present? if field['type'] == 'checkbox'
      [field['key'], value]
    end
  end
end
