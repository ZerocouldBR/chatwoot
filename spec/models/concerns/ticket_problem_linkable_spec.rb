require 'rails_helper'

RSpec.describe TicketProblemLinkable do
  let(:account) { create(:account) }
  let(:agent) { create(:user, account: account, role: :administrator) }
  let(:problem) { create(:conversation, account: account, ticket_type: :problem, assignee: agent, status: :open) }
  let(:incident) { create(:conversation, account: account, ticket_type: :incident, status: :open) }

  it 'links incidents only to problem tickets' do
    other = create(:conversation, account: account, ticket_type: :question)

    expect(incident.update(problem: other)).to be(false)
    expect(incident.update(problem: problem)).to be(true)
  end

  it 'solves the unsolved incidents with the last public reply of the problem' do
    incident.update!(problem: problem)
    create(:message, conversation: problem, account: account, inbox: problem.inbox, message_type: :outgoing, sender: agent,
                     content: 'Corrigimos a falha')

    perform_enqueued_jobs { problem.update!(status: :resolved) }

    expect(incident.reload.status).to eq('resolved')
    expect(incident.messages.outgoing.last.content).to eq('Corrigimos a falha')
  end
end
