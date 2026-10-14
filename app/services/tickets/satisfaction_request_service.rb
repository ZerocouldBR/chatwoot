# Sends the satisfaction survey of a solved ticket when a rule asks for it (Zendesk "Request customer satisfaction
# rating"), through the ticket's channel like the inbox survey, whether or not the inbox sends surveys on its own.
class Tickets::SatisfactionRequestService < CsatSurveyService
  private

  def should_send_csat_survey?
    conversation_allows_csat? && !csat_already_sent?
  end
end
