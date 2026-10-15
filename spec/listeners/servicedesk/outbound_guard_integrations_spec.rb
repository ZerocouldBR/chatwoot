require 'rails_helper'

# Trava "envio externo bloqueado": webhooks (conta, inbox de API, bot, HMAC), integrações, push, tempo real do
# cliente e link mágico do portal.
describe 'Outbound guard on webhooks, integrations and notifications' do # rubocop:disable RSpec/DescribeClass
  let!(:account) { create(:account) }
  let!(:user) { create(:user, account: account) }
  let!(:inbox) { create(:inbox, account: account) }
  let!(:conversation) { create(:conversation, account: account, inbox: inbox, assignee: user) }
  let!(:message) { create(:message, message_type: 'outgoing', account: account, inbox: inbox, conversation: conversation) }
  let(:message_event) { Events::Base.new(:'message.created', Time.zone.now, message: message) }

  def isolate! = account.update!(outbound_blocked: true)

  describe 'account webhooks (signed with the secret)' do
    let!(:webhook) { create(:webhook, inbox: inbox, account: account) }

    it 'are not enqueued for an isolated account' do
      isolate!
      expect(WebhookJob).not_to receive(:perform_later)

      WebhookListener.instance.message_created(message_event)
    end

    it 'are enqueued as before when the guard is off' do
      expect(WebhookJob).to receive(:perform_later).with(webhook.url, anything, :account_webhook, secret: webhook.secret,
                                                                                                  delivery_id: instance_of(String))

      WebhookListener.instance.message_created(message_event)
    end

    it 'make no HTTP request even from a job queued before the guard (HMAC signed request)' do
      isolate!
      stub = stub_request(:post, webhook.url)

      WebhookJob.perform_now(webhook.url, message.webhook_data.merge(event: 'message_created'), :account_webhook,
                             secret: webhook.secret, delivery_id: SecureRandom.uuid)

      expect(stub).not_to have_been_requested
    end

    it 'make no HTTP request with SD_OUTBOUND_BLOCKED, even without the account in the payload' do
      stub = stub_request(:post, 'https://hooks.example.com/x')

      with_modified_env SD_OUTBOUND_BLOCKED: 'true' do
        WebhookJob.perform_now('https://hooks.example.com/x', { event: 'ping' })
      end

      expect(stub).not_to have_been_requested
    end
  end

  describe 'API inbox webhook' do
    let(:api_channel) { create(:channel_api, account: account, webhook_url: 'https://api-inbox.example.com/hook') }
    let(:api_conversation) { create(:conversation, account: account, inbox: api_channel.inbox) }
    let(:api_message) { create(:message, message_type: 'outgoing', account: account, inbox: api_channel.inbox, conversation: api_conversation) }

    it 'is not enqueued for an isolated account' do
      isolate!
      expect(WebhookJob).not_to receive(:perform_later)

      WebhookListener.instance.message_created(Events::Base.new(:'message.created', Time.zone.now, message: api_message))
    end
  end

  describe 'agent bot webhook' do
    let(:agent_bot) { create(:agent_bot, account: account, outgoing_url: 'https://bot.example.com') }

    before { create(:agent_bot_inbox, agent_bot: agent_bot, inbox: inbox) }

    it 'is not enqueued for an isolated account' do
      isolate!
      expect(AgentBots::WebhookJob).not_to receive(:perform_later)

      AgentBotListener.instance.message_created(message_event)
    end

    it 'is enqueued as before when the guard is off' do
      expect(AgentBots::WebhookJob).to receive(:perform_later).once

      AgentBotListener.instance.message_created(message_event)
    end
  end

  describe 'integrations (Slack)' do
    let!(:hook) { create(:integrations_hook, account: account) }

    it 'are not enqueued for an isolated account' do
      isolate!
      expect(HookJob).not_to receive(:perform_later)

      HookListener.instance.message_created(message_event)
    end

    it 'do nothing from a job queued before the guard' do
      isolate!
      expect(SendOnSlackJob).not_to receive(:perform_later)

      HookJob.perform_now(hook, 'message.created', message: message)
    end
  end

  describe 'push notifications' do
    let(:notification) { build(:notification, account: account, user: user, primary_actor: conversation) }

    before do
      setting = user.notification_settings.find_by(account_id: account.id)
      setting.selected_push_flags = [:push_conversation_assignment]
      setting.selected_email_flags = [:email_conversation_assignment]
      setting.save!
    end

    it 'send no push nor e-mail for an isolated account, but keep the in-app notification' do
      isolate!

      expect { notification.save! }.not_to have_enqueued_job(Notification::PushNotificationJob)
      expect(Notification::EmailNotificationJob).not_to have_been_enqueued
      expect(notification).to be_persisted
    end

    it 'send push and e-mail as before when the guard is off' do
      expect { notification.save! }.to have_enqueued_job(Notification::PushNotificationJob)
        .and have_enqueued_job(Notification::EmailNotificationJob)
    end

    it 'send no web push from a job queued before the guard' do
      notification.save!
      create(:notification_subscription, user: user)
      isolate!
      expect(WebPush).not_to receive(:payload_send)

      Notification::PushNotificationService.new(notification: notification).perform
    end
  end

  describe 'customer real time (widget / client API)' do
    it 'goes only to the agents for an isolated account' do
      create(:inbox_member, user: user, inbox: inbox)
      isolate!
      contact_token = conversation.contact_inbox.pubsub_token

      expect { ActionCableListener.instance.message_created(message_event) }
        .to have_enqueued_job(ActionCableBroadcastJob).with(satisfy { |tokens| tokens.include?(user.pubsub_token) && tokens.exclude?(contact_token) },
                                                            any_args)
    end
  end

  describe 'portal magic link' do
    let(:portal) { create(:portal, account: account) }

    it 'sends no e-mail for an isolated account' do
      create(:contact, account: account, email: 'cliente@example.com')
      isolate!

      with_modified_env SD_PORTAL_LOGIN_EMAIL_ENABLED: 'true' do
        expect { PortalCustomers::MagicLinkService.new(portal: portal).request!(email: 'cliente@example.com', locale: 'pt_BR') }
          .not_to have_enqueued_mail(PortalCustomerMailer, :magic_link)
      end
    end
  end
end
