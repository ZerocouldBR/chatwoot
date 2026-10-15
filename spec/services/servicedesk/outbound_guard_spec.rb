require 'rails_helper'

describe Servicedesk::OutboundGuard do
  let!(:account) { create(:account) }
  let!(:other_account) { create(:account) }
  let(:mailer) do
    Class.new(ApplicationMailer) do
      def self.name = 'SdGuardTestMailer'

      def hello(account)
        @account = account
        mail(to: 'cliente@example.com', subject: 'Olá', body: 'corpo')
      end
    end
  end

  around do |example|
    # Sem SMTP_ADDRESS o initializer do mailer troca o :test por :sendmail.
    original = ActionMailer::Base.delivery_method
    ActionMailer::Base.delivery_method = :test
    example.run
  ensure
    ActionMailer::Base.delivery_method = original
  end

  before do
    stub_const('SdGuardTestMailer', mailer)
    ActionMailer::Base.deliveries.clear
  end

  describe '.blocked?' do
    it 'is false by default' do
      expect(described_class.blocked?(account)).to be(false)
      expect(account.servicedesk_outbound_blocked?).to be(false)
    end

    it 'follows the account setting' do
      account.update!(outbound_blocked: true)

      expect(described_class.blocked?(account)).to be(true)
      expect(described_class.blocked?(account.id)).to be(true)
      expect(described_class.blocked?(other_account)).to be(false)
    end

    it 'blocks every account with SD_OUTBOUND_BLOCKED' do
      with_modified_env SD_OUTBOUND_BLOCKED: 'true' do
        expect(described_class.blocked?(other_account)).to be(true)
        expect(described_class.blocked?).to be(true)
      end
    end

    it 'resolves the account of a conversation' do
      account.update!(outbound_blocked: true)
      conversation = create(:conversation, account: account)

      expect(described_class.blocked?(conversation)).to be(true)
    end

    it 'rejects a non boolean setting' do
      account.outbound_blocked = 'sim'

      expect(account).not_to be_valid
    end
  end

  describe 'e-mails' do
    it 'delivers when the guard is off and strips the internal header' do
      SdGuardTestMailer.hello(account).deliver_now

      expect(ActionMailer::Base.deliveries.size).to eq(1)
      expect(ActionMailer::Base.deliveries.first.header[described_class::ACCOUNT_HEADER]).to be_nil
    end

    it 'enqueues deliver_later when the guard is off' do
      expect { SdGuardTestMailer.hello(account).deliver_later }.to have_enqueued_job(ActionMailer::MailDeliveryJob)
    end

    it 'does not deliver e-mails of an isolated account' do
      account.update!(outbound_blocked: true)

      SdGuardTestMailer.hello(account).deliver_now
      SdGuardTestMailer.hello(other_account).deliver_now

      expect(ActionMailer::Base.deliveries.size).to eq(1)
    end

    it 'does not even enqueue deliver_later of an isolated account' do
      account.update!(outbound_blocked: true)

      expect { SdGuardTestMailer.hello(account).deliver_later }.not_to have_enqueued_job(ActionMailer::MailDeliveryJob)
      expect { SdGuardTestMailer.with(account: account).hello(account).deliver_later }.not_to have_enqueued_job
    end

    it 'blocks every e-mail with SD_OUTBOUND_BLOCKED, including Devise' do
      user = create(:user, skip_confirmation: true)
      ActionMailer::Base.deliveries.clear
      with_modified_env SD_OUTBOUND_BLOCKED: 'true' do
        expect { SdGuardTestMailer.hello(account).deliver_later }.not_to have_enqueued_job
        SdGuardTestMailer.hello(account).deliver_now
        user.send_reset_password_instructions
      end

      expect(ActionMailer::Base.deliveries).to be_empty
    end
  end
end
