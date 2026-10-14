# Business hours and holidays of an account (Zendesk "schedule").
# Intervals are weekly: { day: 0..6 (Sunday first), start/end: minutes from midnight, 15-minute steps }.
class BusinessSchedule < ApplicationRecord
  MINUTE_STEP = 15
  MINUTES_PER_DAY = 1440
  # Bounds the day-by-day walk when a schedule has very few open hours.
  MAX_DAYS_SCANNED = 800

  belongs_to :account

  validates :name, presence: true
  validates :time_zone, inclusion: { in: ActiveSupport::TimeZone::MAPPING.values | ActiveSupport::TimeZone::MAPPING.keys }
  validate :intervals_are_valid
  validate :holidays_are_valid

  before_save :unset_other_defaults, if: -> { is_default? && will_save_change_to_is_default? }

  def self.default_for(account)
    find_by(account_id: account.id, is_default: true)
  end

  # Business seconds between two instants.
  def elapsed_seconds(from, to)
    return 0 if to <= from

    each_open_range(from) do |range_start, range_end, total|
      return total if to <= range_start
      return total + (to - range_start).to_i if to <= range_end

      total + (range_end - range_start).to_i
    end
  end

  # The instant reached after `seconds` of business time from `from`.
  def add_seconds(from, seconds)
    remaining = seconds
    each_open_range(from) do |range_start, range_end|
      length = (range_end - range_start).to_i
      return range_start + remaining if remaining <= length

      remaining -= length
    end
  end

  def open_at?(time)
    local = time.in_time_zone(time_zone)
    minute = (local.hour * 60) + local.min
    !holiday?(local.to_date) && intervals_for(local.wday).any? { |interval| minute >= interval['start'] && minute < interval['end'] }
  end

  private

  # Yields each open range from `from` onwards (clipped to start at `from`), with the running total
  # returned by the previous yield, so callers can stop as soon as they are done.
  def each_open_range(from)
    zone = ActiveSupport::TimeZone[time_zone]
    date = from.in_time_zone(zone).to_date
    total = 0
    MAX_DAYS_SCANNED.times do
      open_ranges(date, zone).each do |range_start, range_end|
        next if range_end <= from

        total = yield([range_start, from].max, range_end, total)
      end
      date += 1
    end
    raise ArgumentError, "schedule #{id} has no business hours in #{MAX_DAYS_SCANNED} days"
  end

  def open_ranges(date, zone)
    return [] if holiday?(date)

    midnight = zone.local(date.year, date.month, date.day)
    intervals_for(date.wday).map { |interval| [midnight + interval['start'].minutes, midnight + interval['end'].minutes] }
  end

  def intervals_for(wday)
    intervals.select { |interval| interval['day'] == wday }.sort_by { |interval| interval['start'] }
  end

  def holiday?(date)
    holidays.any? { |holiday| date.between?(Date.parse(holiday['start_date']), Date.parse(holiday['end_date'])) }
  end

  def intervals_are_valid
    return errors.add(:intervals, :blank) if intervals.blank?
    return errors.add(:intervals, :invalid) unless intervals.all? { |interval| valid_interval?(interval) }

    errors.add(:intervals, :invalid) if overlapping_intervals?
  end

  def overlapping_intervals?
    intervals.group_by { |interval| interval['day'] }.values.any? do |day_intervals|
      day_intervals.sort_by { |interval| interval['start'] }.each_cons(2).any? { |first, second| second['start'] < first['end'] }
    end
  end

  def valid_interval?(interval)
    start, finish, day = interval.values_at('start', 'end', 'day')
    [start, finish, day].all?(Integer) && day.between?(0, 6) && start >= 0 && finish <= MINUTES_PER_DAY && start < finish &&
      (start % MINUTE_STEP).zero? && (finish % MINUTE_STEP).zero?
  end

  def holidays_are_valid
    valid = holidays.all? do |holiday|
      holiday['name'].present? && Date.parse(holiday['start_date']) <= Date.parse(holiday['end_date'])
    rescue ArgumentError, TypeError
      false
    end
    errors.add(:holidays, :invalid) unless valid
  end

  def unset_other_defaults
    self.class.where(account_id: account_id, is_default: true).where.not(id: id).update_all(is_default: false) # rubocop:disable Rails/SkipsModelValidations
  end
end
