# ServiceDesk B2B: anexos enviados pelo cliente no portal (nova solicitação e resposta).
# Usa as mesmas regras do widget do site (Attachment::ACCEPTABLE_FILE_TYPES, imagem, vídeo e áudio, e o
# limite MAXIMUM_FILE_UPLOAD_SIZE). SVG e HTML são recusados porque podem conter script.
class PortalCustomers::AttachmentBuilder
  include FileTypeHelper

  BLOCKED_TYPES = %w[image/svg+xml text/html application/xhtml+xml application/javascript text/javascript].freeze

  pattr_initialize [:message!, :uploads!]

  def self.error_messages(record)
    messages = Array(record&.errors&.full_messages)
    messages = [I18n.t('public_portal.sd.requests.errors.attachment_invalid')] if messages.empty?
    messages
  end

  def build
    uploads.each do |upload|
      validate!(upload)
      message.attachments.new(account_id: message.account_id, file_type: file_type(upload.content_type), file: upload)
    end
  end

  private

  def validate!(upload)
    name = upload.original_filename.to_s
    raise_error(:attachment_too_big, name) if upload.size > limit_bytes
    raise_error(:attachment_type, name) unless acceptable?(upload.content_type.to_s, name)
  end

  def raise_error(key, name)
    raise PortalCustomers::CreateRequestService::Error,
          I18n.t("public_portal.sd.requests.errors.#{key}", file: name, size: limit_bytes / 1.megabyte)
  end

  def acceptable?(content_type, name)
    return false if BLOCKED_TYPES.include?(content_type)
    return true if content_type.start_with?('image/', 'video/', 'audio/')
    return true if Attachment::ACCEPTABLE_FILE_TYPES.include?(content_type)

    Attachment::GENERIC_FILE_CONTENT_TYPES.include?(content_type) &&
      Attachment::ACCEPTABLE_FILE_EXTENSIONS.include?(File.extname(name).delete('.').downcase)
  end

  def limit_bytes
    limit_mb = GlobalConfigService.load('MAXIMUM_FILE_UPLOAD_SIZE', 40).to_i
    limit_mb = 40 if limit_mb <= 0
    limit_mb.megabytes
  end
end
