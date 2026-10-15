class Campaigns::TriggerOneoffCampaignJob < ApplicationJob
  queue_as :low

  def perform(campaign)
    return Servicedesk::OutboundGuard.log('campaign', campaign.account_id) if Servicedesk::OutboundGuard.blocked?(campaign.account)

    campaign.trigger!
  end
end
