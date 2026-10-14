# POST /api/v2/uploads: guarda o arquivo como blob do ActiveStorage e devolve o token do Zendesk
# (= signed id do blob, válido por TOKEN_TTL). O token entra em comment.uploads de um PUT/POST de ticket.
# rubocop:disable Metrics/CyclomaticComplexity
module ZendeskCompat::Uploads
  TOKEN_TTL = 3.days
  MAX_SIZE = 50.megabytes

  module_function

  def create(io:, filename:, content_type:)
    raise ZendeskCompat::Error, 'Arquivo vazio' if io.nil? || io.size.to_i.zero?
    raise ZendeskCompat::Error, "Arquivo maior que #{MAX_SIZE / 1.megabyte} MB" if io.size.to_i > MAX_SIZE

    name = File.basename(filename.to_s.presence || 'arquivo')
    type = content_type.presence
    type = Marcel::MimeType.for(io, name: name) if type.blank? || type == 'application/octet-stream' || type.start_with?('application/x-www-form')
    ActiveStorage::Blob.create_and_upload!(io: io, filename: name, content_type: type)
  end

  def token(blob)
    blob.signed_id(expires_in: TOKEN_TTL)
  end

  def find(token)
    ActiveStorage::Blob.find_signed(token.to_s)
  end
end
# rubocop:enable Metrics/CyclomaticComplexity
