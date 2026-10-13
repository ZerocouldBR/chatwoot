require 'rails_helper'

RSpec.describe Servicedesk::AccountMacroSettings do
  let(:account) { create(:account) }

  describe '#macro_fill_editor?' do
    it 'is on by default in the ServiceDesk installation' do
      expect(account.macro_fill_editor).to be_nil
      expect(account.macro_fill_editor?).to be(true)
    end

    it 'follows SD_MACRO_FILL_EDITOR when the account has no value' do
      with_modified_env(SD_MACRO_FILL_EDITOR: 'false') do
        expect(account.macro_fill_editor?).to be(false)
      end
    end

    it 'prefers the account setting' do
      account.update!(macro_fill_editor: false)

      with_modified_env(SD_MACRO_FILL_EDITOR: 'true') do
        expect(account.reload.macro_fill_editor?).to be(false)
      end
    end

    it 'normalizes string values sent by forms' do
      account.settings['macro_fill_editor'] = 'false'
      account.save!

      expect(account.reload.settings['macro_fill_editor']).to be(false)
    end

    it 'rejects values that are not booleans' do
      account.macro_fill_editor = 'talvez'

      expect(account).not_to be_valid
    end
  end
end
