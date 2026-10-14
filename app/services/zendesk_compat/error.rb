# Erros da API de compatibilidade, devolvidos no formato do Zendesk por ZendeskCompat::BaseController.
class ZendeskCompat::Error < StandardError
  def status = :bad_request
  def body = { error: 'InvalidParameter', description: message }

  class RecordInvalid < ZendeskCompat::Error
    attr_reader :details

    def initialize(details)
      @details = details
      super('Record validation errors')
    end

    def status = :unprocessable_entity
    def body = { error: 'RecordInvalid', description: 'Record validation errors', details: details }
  end

  class UpdateConflict < ZendeskCompat::Error
    def initialize(msg = 'Safe Update prevented the update due to outdated ticket data. Please fetch the latest ticket data and try again.')
      super
    end

    def status = :conflict
    def body = { error: 'UpdateConflict', description: message }
  end

  class NotFound < ZendeskCompat::Error
    def initialize(msg = 'Not found')
      super
    end

    def status = :not_found
    def body = { error: 'RecordNotFound', description: message }
  end

  class Unsupported < ZendeskCompat::Error
    def body = { error: 'UnsupportedByServiceDesk', description: message }
  end
end
