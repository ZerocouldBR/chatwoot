# Solves the unsolved incidents of a solved problem ticket, adding the problem's last public reply to each one.
class Tickets::SolveIncidentsJob < ApplicationJob
  queue_as :medium

  def perform(problem_id)
    problem = Conversation.find(problem_id)
    reply = problem.messages.outgoing.where(private: false).last
    agent = reply&.sender.is_a?(User) ? reply.sender : problem.assignee

    problem.incidents.where(status: Conversation::UNSOLVED_STATUSES).find_each do |incident|
      Messages::MessageBuilder.new(agent, incident, { content: reply.content, private: false }).perform if reply&.content.present?
      incident.update!(status: :resolved, assignee: incident.assignee || agent)
    end
  end
end
