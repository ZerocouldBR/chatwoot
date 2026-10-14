# POST /api/v2/uploads(.json)?filename=nome  (corpo = bytes do arquivo, como o n8n manda em "binaryData";
# também aceita multipart com o campo "uploaded_data"/"file"). DELETE /api/v2/uploads/:token descarta o arquivo.
class ZendeskCompat::V2::UploadsController < ZendeskCompat::BaseController
  def create
    io, filename, content_type = upload_source
    blob = ZendeskCompat::Uploads.create(io: io, filename: params[:filename].presence || filename, content_type: content_type)
    attachment = ZendeskCompat::CommentPresenter.new(context).blob_json(blob, id: blob.id)
    token = ZendeskCompat::Uploads.token(blob)
    render json: { upload: { token: token, expires_at: context.time(ZendeskCompat::Uploads::TOKEN_TTL.from_now), attachment: attachment,
                             attachments: [attachment] } }, status: :created
  end

  def destroy
    blob = ZendeskCompat::Uploads.find(params[:id]) || raise(ZendeskCompat::Error::NotFound)
    blob.purge_later unless ActiveStorage::Attachment.exists?(blob_id: blob.id)
    head :no_content
  end

  private

  def upload_source
    file = params[:uploaded_data] || params[:file]
    return [file.tempfile, file.original_filename, file.content_type] if file.respond_to?(:tempfile)

    request.body.rewind
    raw = request.body.read
    raise ZendeskCompat::Error, 'Corpo vazio: envie o arquivo no corpo da requisição' if raw.blank?

    [StringIO.new(raw), 'arquivo', request.content_type]
  end
end
