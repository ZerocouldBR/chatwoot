# Converte as mudanças salvas de uma conversa (saved_changes) em eventos Change no formato do Zendesk:
#   status / custom_status_id (categoria e status personalizado), assignee_id (id do Zendesk do agente ou bot),
#   group_id (time), priority, tags (lista) e campos personalizados (field_name = id do campo, valor = tag/valor).
# Valores como texto, como no Zendesk ("value": "36212918767515").
class Servicedesk::TicketAuditEvents
  Snapshot = Struct.new(:status, :custom_attributes) do
    def resolved? = status == 'resolved'
    def pending? = status == 'pending'
  end

  PRIORITIES = { 'low' => 'low', 'medium' => 'normal', 'high' => 'high', 'urgent' => 'urgent' }.freeze

  def initialize(conversation, changes)
    @conversation = conversation
    @changes = changes
  end

  def build
    status_events + assignee_events + group_events + priority_events + tag_events + field_events
  end

  private

  def change(field, previous, value)
    return [] if previous == value

    [{ 'type' => 'Change', 'field_name' => field, 'value' => value, 'previous_value' => previous }]
  end

  def before_after(key)
    @changes.key?(key) ? @changes[key] : [@conversation.public_send(key), @conversation.public_send(key)]
  end

  def status_events
    return [] unless @changes.key?('status') || @changes.key?('custom_attributes')

    old_status, new_status = before_after('status')
    old_attrs, new_attrs = before_after('custom_attributes')
    before = Snapshot.new(old_status, old_attrs || {})
    after = Snapshot.new(new_status, new_attrs || {})
    translator = ZendeskCompat::StatusTranslator
    change('status', translator.category(before), translator.category(after)) +
      change('custom_status_id', translator.custom_status_id(before)&.to_s, translator.custom_status_id(after)&.to_s)
  end

  def assignee_events
    return [] unless @changes.key?('assignee_id') || @changes.key?('assignee_agent_bot_id')

    change('assignee_id', assignee_zid(*previous_assignee), assignee_zid(@conversation.assignee_id, agent_bot_id))
  end

  def previous_assignee
    [before_after('assignee_id').first, bot_id(before_after('assignee_agent_bot_id').first, before_after('ai_assignee_type').first)]
  end

  def agent_bot_id
    bot_id(@conversation.assignee_agent_bot_id, @conversation.ai_assignee_type)
  end

  # assignee_agent_bot_id é polimórfico (ai_assignee_type): só AgentBot vira responsável no formato do Zendesk.
  def bot_id(id, type)
    id if type.blank? || type == 'AgentBot'
  end

  def assignee_zid(user_id, bot_id)
    record = (user_id && User.find_by(id: user_id)) || (bot_id && AgentBot.find_by(id: bot_id))
    record && ZendeskCompat::Ids.user_id(record).to_s
  end

  def group_events
    return [] unless @changes.key?('team_id')

    directory = ZendeskCompat::Directory.new(@conversation.account)
    old_id, new_id = @changes['team_id']
    change('group_id', old_id && directory.group_id(Team.find_by(id: old_id))&.to_s, new_id && directory.group_id(Team.find_by(id: new_id))&.to_s)
  end

  def priority_events
    return [] unless @changes.key?('priority')

    old_value, new_value = @changes['priority']
    change('priority', PRIORITIES[old_value], PRIORITIES[new_value])
  end

  def tag_events
    return [] unless @changes.key?('cached_label_list')

    old_value, new_value = @changes['cached_label_list'].map { |list| list.to_s.split(',').map(&:strip).compact_blank.sort }
    change('tags', old_value, new_value)
  end

  def field_events
    return [] unless @changes.key?('custom_attributes')

    old_attrs, new_attrs = @changes['custom_attributes'].map { |attrs| attrs || {} }
    translator = ZendeskCompat::FieldTranslator.new(@conversation.account)
    ZendeskCompat::Config.custom_ticket_fields.flat_map do |field|
      key = translator.attribute_key(field)
      next [] if key.nil? || old_attrs[key] == new_attrs[key]

      change(field['id'].to_s, translator.zendesk_value(field, old_attrs[key]), translator.zendesk_value(field, new_attrs[key]))
    end
  end
end
