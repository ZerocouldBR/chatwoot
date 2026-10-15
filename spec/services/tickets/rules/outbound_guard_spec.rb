require 'rails_helper'

# Trava "envio externo bloqueado" no motor de regras: gatilhos, gatilhos com atraso e automações.
RSpec.describe 'Ticket rules with the outbound guard' do # rubocop:disable RSpec/DescribeClass
  let(:account) { create(:account) }
  let(:outbound_job_names) { %w[ActionMailer::MailDeliveryJob WebhookJob AgentBots::WebhookJob SendReplyJob HookJob] }
  let(:team) { create(:team, account: account) }
  let(:agent) { create(:user, account: account, role: :agent) }
  let(:conversation) { create(:conversation, account: account, priority: nil, team: team, assignee: agent) }
  let(:notify_actions) do
    [{ field: 'email_requester_and_ccs', value: { subject: 'Pedido #{{ticket.id}}', body: 'Recebido' } },
     { field: 'email_group', value: { subject: 'Novo', body: 'Novo ticket' } },
     { field: 'email_assignee', value: { subject: 'Seu', body: 'Seu ticket' } },
     { field: 'notify_webhook', value: 'https://n8n.example.com/webhook/ia' },
     { field: 'send_message', value: 'Recebemos o ticket #{{ticket.id}}' }]
  end

  before do
    conversation.contact.update!(email: 'cliente@example.com')
    create(:team_member, team: team, user: agent)
    TicketRule.create!(account: account, kind: :trigger, title: 'Notificar tudo', position: 1,
                       conditions: { all: [{ field: 'ticket', operator: 'is', value: 'created' }], any: [] }, actions: notify_actions)
  end

  def run_triggers
    Tickets::Rules::TriggerRunner.new(conversation).perform
  end

  def outbound_jobs
    ActiveJob::Base.queue_adapter.enqueued_jobs.count { |job| outbound_job_names.include?(job[:job].to_s) }
  end

  context 'when the account is isolated' do
    before { account.update!(outbound_blocked: true) }

    it 'sends no e-mail, calls no webhook and keeps the reply marked as not sent' do
      conversation
      ActiveJob::Base.queue_adapter.enqueued_jobs.clear
      run_triggers
      expect(outbound_jobs).to eq(0)

      reply = conversation.messages.outgoing.last
      expect(reply).to have_attributes(content: "Recebemos o ticket ##{conversation.display_id}", status: 'failed')
      expect(reply.outbound_blocked?).to be(true)
      expect(conversation.messages.activity.pluck(:content)).to include(
        a_string_including('Notificar tudo'), a_string_including('webhook')
      )
      expect(conversation.conversation_events.where(event_type: 'outbound_blocked').pluck(:field_name))
        .to contain_exactly('email_requester_and_ccs', 'email_group', 'email_assignee', 'notify_webhook', 'message')
    end

    it 'delivers nothing even if the queued jobs run' do
      ActionMailer::Base.deliveries.clear
      perform_enqueued_jobs { run_triggers }

      expect(ActionMailer::Base.deliveries).to be_empty
      expect(a_request(:any, /n8n\.example\.com/)).not_to have_been_made
    end

    it 'blocks the e-mails of an automation' do
      conversation.update!(status: :waiting_on_customer)
      conversation.update_columns(status_changed_at: 30.hours.ago) # rubocop:disable Rails/SkipsModelValidations
      automation = TicketRule.create!(
        account: account, kind: :automation, title: 'Lembrete', position: 1,
        conditions: { all: [{ field: 'status', operator: 'is', value: 'waiting_on_customer' },
                            { field: 'hours_since_waiting_on_customer', operator: 'greater_than', value: '24' }], any: [] },
        actions: [{ field: 'email_requester', value: { subject: 'Lembrete', body: 'Responda' } }, { field: 'status', value: 'on_hold' }]
      )

      expect { Tickets::Rules::AutomationRunner.new(automation).perform }
        .not_to have_enqueued_mail(TicketRequesterMailer, :ticket_notification)
      expect(conversation.reload.status).to eq('on_hold')
      expect(conversation.conversation_events.where(event_type: 'outbound_blocked').pluck(:field_name)).to eq(['email_requester'])
    end

    it 'keeps the satisfaction survey in the ticket without sending it' do
      conversation.update!(status: :resolved)

      expect { Tickets::SatisfactionRequestService.new(conversation: conversation).perform }.not_to have_enqueued_job(SendReplyJob)

      survey = conversation.messages.where(content_type: :input_csat).last
      expect(survey.outbound_blocked?).to be(true)
    end
  end

  context 'when the guard is off' do
    it 'e-mails, calls the webhook and sends the reply as before' do
      expect { run_triggers }
        .to have_enqueued_mail(TicketRequesterMailer, :ticket_notification)
        .and have_enqueued_mail(TicketRuleMailer, :agent_notification)
        .and have_enqueued_job(WebhookJob).with('https://n8n.example.com/webhook/ia', anything)
        .and have_enqueued_job(SendReplyJob)

      expect(conversation.messages.outgoing.last.outbound_blocked?).to be(false)
      expect(conversation.conversation_events.where(event_type: 'outbound_blocked')).to be_empty
    end
  end
end
