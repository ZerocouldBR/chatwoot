# Runs one automation over the account's tickets that are not closed (Zendesk: hourly, up to 1,000 tickets per run).
# Each ticket it changes is one update, so triggers run on it afterwards.
class Tickets::Rules::AutomationRunner
  MAX_TICKETS = 1000

  def initialize(automation, now: Time.current)
    @automation = automation
    @now = now
  end

  def perform
    matched = 0
    candidates.find_each do |conversation|
      break if matched >= MAX_TICKETS
      next unless @automation.matches?(conversation, now: @now)

      matched += 1
      deferred = Tickets::Rules::ActionApplier.new(@automation, conversation).perform
      Tickets::Rules::Notifier.new(conversation.reload, deferred).perform if deferred.any?
    end
  end

  private

  # Narrows the scan with the "status is" conditions every automation of this kind usually has.
  def candidates
    scope = Conversation.where(account_id: @automation.account_id).where.not(status: :closed)
    statuses = @automation.conditions.fetch('all', []).select { |c| c['field'] == 'status' && c['operator'] == 'is' }.pluck('value')
    statuses.any? ? scope.where(status: statuses) : scope
  end
end
