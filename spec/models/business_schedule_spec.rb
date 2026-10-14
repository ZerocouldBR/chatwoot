require 'rails_helper'

RSpec.describe BusinessSchedule do
  let(:account) { create(:account) }
  # Monday to Friday, 09:00-12:00 and 13:00-18:00, São Paulo time.
  let(:weekdays) do
    (1..5).flat_map { |day| [{ 'day' => day, 'start' => 540, 'end' => 720 }, { 'day' => day, 'start' => 780, 'end' => 1080 }] }
  end
  let(:schedule) do
    described_class.create!(account: account, name: 'Comercial', time_zone: 'America/Sao_Paulo', intervals: weekdays,
                            holidays: [{ 'name' => 'Natal', 'start_date' => '2026-12-25', 'end_date' => '2026-12-25' }])
  end
  let(:zone) { ActiveSupport::TimeZone['America/Sao_Paulo'] }

  describe '#elapsed_seconds' do
    it 'counts only open hours, skipping lunch' do
      expect(schedule.elapsed_seconds(zone.local(2026, 10, 12, 11), zone.local(2026, 10, 12, 14))).to eq(2.hours)
    end

    it 'skips nights and weekends' do
      # Friday 17:00 to Monday 10:00 = 1h on Friday + 1h on Monday.
      expect(schedule.elapsed_seconds(zone.local(2026, 10, 16, 17), zone.local(2026, 10, 19, 10))).to eq(2.hours)
    end

    it 'skips holidays' do
      # Thursday 24/12 17:00 to Monday 28/12 10:00, with Friday 25/12 off.
      expect(schedule.elapsed_seconds(zone.local(2026, 12, 24, 17), zone.local(2026, 12, 28, 10))).to eq(2.hours)
    end

    it 'is zero when both instants fall in the same closed period' do
      expect(schedule.elapsed_seconds(zone.local(2026, 10, 17, 10), zone.local(2026, 10, 18, 10))).to eq(0)
    end
  end

  describe '#add_seconds' do
    it 'moves a target past closed hours' do
      # 4 business hours from Friday 16:00 -> 2h on Friday, 2h on Monday -> Monday 11:00.
      expect(schedule.add_seconds(zone.local(2026, 10, 16, 16), 4.hours)).to eq(zone.local(2026, 10, 19, 11))
    end

    it 'starts counting at the next opening when started while closed' do
      expect(schedule.add_seconds(zone.local(2026, 10, 17, 22), 30.minutes)).to eq(zone.local(2026, 10, 19, 9, 30))
    end

    it 'respects the schedule time zone' do
      from = Time.utc(2026, 10, 12, 11) # 08:00 in São Paulo, before opening
      expect(schedule.add_seconds(from, 1.hour)).to eq(zone.local(2026, 10, 12, 10))
    end
  end

  describe '#open_at?' do
    it 'tells open from closed times' do
      expect(schedule.open_at?(zone.local(2026, 10, 12, 10))).to be(true)
      expect(schedule.open_at?(zone.local(2026, 10, 12, 12, 30))).to be(false)
      expect(schedule.open_at?(zone.local(2026, 12, 25, 10))).to be(false)
    end
  end

  describe 'validations' do
    it 'rejects intervals off the 15-minute grid, inverted or overlapping' do
      [[{ 'day' => 1, 'start' => 545, 'end' => 600 }],
       [{ 'day' => 1, 'start' => 600, 'end' => 540 }],
       [{ 'day' => 1, 'start' => 540, 'end' => 720 }, { 'day' => 1, 'start' => 700, 'end' => 800 }]].each do |intervals|
        expect(described_class.new(account: account, name: 'X', time_zone: 'UTC', intervals: intervals)).not_to be_valid
      end
    end

    it 'keeps a single default schedule per account' do
      first = described_class.create!(account: account, name: 'A', time_zone: 'UTC', intervals: weekdays, is_default: true)
      second = described_class.create!(account: account, name: 'B', time_zone: 'UTC', intervals: weekdays, is_default: true)

      expect(first.reload.is_default).to be(false)
      expect(described_class.default_for(account)).to eq(second)
    end
  end
end
