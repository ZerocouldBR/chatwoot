require 'rails_helper'

RSpec.describe TicketRequesterMailer do
  let(:account) { create(:account) }

  it 'e-mails the requester of a chat ticket without e-mail thread headers' do
    with_modified_env SMTP_ADDRESS: 'smtp.example.com' do
      conversation = create(:conversation, account: account, inbox: create(:inbox, account: account))
      conversation.contact.update!(email: 'cliente@example.com')

      mail = described_class.with(account: account).ticket_notification(conversation, to: 'cliente@example.com', cc: [], subject: 'Recebido',
                                                                                      body: 'Olá').deliver_now

      expect(mail.to).to eq(['cliente@example.com'])
      expect(mail.in_reply_to).to be_nil
    end
  end
end
