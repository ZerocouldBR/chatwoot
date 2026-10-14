require 'rails_helper'

RSpec.describe Tickets::SatisfactionRequestService do
  let(:account) { create(:account) }
  let(:inbox) { create(:inbox, account: account, csat_survey_enabled: false) }
  let(:conversation) { create(:conversation, account: account, inbox: inbox, status: :resolved) }

  it 'sends the Good/Bad survey even when the inbox does not send surveys itself and marks it offered' do
    described_class.new(conversation: conversation).perform

    survey = conversation.messages.find_by(content_type: :input_csat)
    expect(survey.content_attributes['display_type']).to eq('good_bad')
    expect(conversation.reload).to be_satisfaction_offered
  end

  it 'records the rating as good or bad' do
    described_class.new(conversation: conversation).perform
    survey = conversation.messages.find_by(content_type: :input_csat)

    perform_enqueued_jobs do
      survey.update!(content_attributes: survey.content_attributes.merge(
        'submitted_values' => { 'csat_survey_response' => { 'rating' => 1, 'feedback_message' => 'Demorou' } }
      ))
    end

    expect(conversation.reload).to be_satisfaction_bad
    expect(conversation.satisfaction_comment).to eq('Demorou')
  end

  it 'is nullified by the satisfaction condition in automations' do
    automation = TicketRule.new(account: account, kind: :automation, title: 'CSAT',
                                conditions: { all: [{ field: 'satisfaction', operator: 'is', value: 'unoffered' },
                                                    { field: 'hours_since_resolved', operator: 'greater_than', value: '24' }], any: [] },
                                actions: [{ field: 'request_satisfaction', value: '' }])

    expect(automation).to be_valid
  end
end
