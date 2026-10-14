# Zendesk customer satisfaction on a ticket: unoffered until a survey is sent, offered while it waits for an answer,
# then good or bad. Ratings from the 1-5 survey scales count as good from 4 and bad up to 2.
module TicketSatisfaction
  extend ActiveSupport::Concern

  GOOD_RATING = 4
  BAD_RATING = 2

  included do
    has_many :csat_survey_responses, dependent: :destroy_async
    enum satisfaction: { unoffered: 0, offered: 1, good: 2, bad: 3 }, _prefix: :satisfaction
  end

  def offer_satisfaction!
    update!(satisfaction: :offered) if satisfaction_unoffered?
  end

  def rate_satisfaction!(rating)
    score = if rating >= GOOD_RATING then :good
            elsif rating <= BAD_RATING then :bad
            end
    update!(satisfaction: score) if score
  end

  def satisfaction_comment
    csat_survey_responses.order(:id).last&.feedback_message
  end
end
