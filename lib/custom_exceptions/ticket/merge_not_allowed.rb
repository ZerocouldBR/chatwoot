# frozen_string_literal: true

class CustomExceptions::Ticket::MergeNotAllowed < CustomExceptions::Base
  def message
    I18n.t("errors.tickets.merge.#{@data[:reason]}")
  end

  def http_status
    422
  end
end
