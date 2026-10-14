# Permanently redacts a comment, like Zendesk: the given text (or the whole comment) is replaced with blocks
# everywhere the message keeps it (including the original e-mail), and the given attachments are deleted.
# The ticket gets the `redacted_content` tag and a redaction event. There is no undo.
class Tickets::RedactionService
  REDACTED_TAG = 'redacted_content'.freeze
  BLOCK = '▇'.freeze

  pattr_initialize [:message!, :user!, :text, :attachment_ids]

  def perform
    redact_text
    message.attachments.where(id: Array(attachment_ids)).destroy_all
    conversation = message.conversation
    conversation.add_labels([REDACTED_TAG])
    conversation.record_ticket_event(event_type: 'redaction', author: user, via: 'agent',
                                     value: { message_id: message.id, attachments: Array(attachment_ids).size })
    message.reload
  end

  private

  def redact_text
    target = text.presence || message.content
    return if target.blank?

    replacement = BLOCK * target.length
    redact = ->(value) { value.is_a?(String) ? value.gsub(target, replacement) : value }
    message.update!(content: redact.call(message.content), content_attributes: deep_map(message.content_attributes, redact))
  end

  def deep_map(value, redact)
    case value
    when Hash then value.transform_values { |item| deep_map(item, redact) }
    when Array then value.map { |item| deep_map(item, redact) }
    else redact.call(value)
    end
  end
end
