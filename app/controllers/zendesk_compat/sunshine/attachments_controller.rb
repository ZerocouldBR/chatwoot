# POST /sc/v2/apps/:app_id/attachments?access=public&for=message&conversationId=... (multipart, campo "source"):
# guarda o arquivo e devolve {attachment: {mediaUrl, mediaType}} para usar em content.mediaUrl de uma mensagem.
class ZendeskCompat::Sunshine::AttachmentsController < ZendeskCompat::Sunshine::BaseController
  def create
    file = params[:source]
    raise ZendeskCompat::Error, 'Envie o arquivo no campo "source" (multipart)' unless file.respond_to?(:tempfile)

    blob = ZendeskCompat::Uploads.create(io: file.tempfile, filename: file.original_filename, content_type: file.content_type)
    render json: { attachment: { mediaUrl: context.blob_url(blob), mediaType: blob.content_type } }, status: :created
  end
end
