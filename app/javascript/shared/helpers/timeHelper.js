import {
  format,
  isSameYear,
  isThisYear,
  isToday,
  isYesterday,
  fromUnixTime,
  formatDistanceToNow,
  differenceInDays,
} from 'date-fns';
import { de, es, fr, pt, ptBR } from 'date-fns/locale';

const DATE_LOCALES = { de, es, fr, pt, pt_BR: ptBR };
// English-ordered patterns callers pass, rewritten day-first (24h) for other locales.
const DAY_FIRST_PATTERNS = [
  ['h:mm a', 'HH:mm'],
  ['MMM d, yyyy', 'd MMM yyyy'],
  ['LLL d y', 'd LLL y'],
  ['LLL d', 'd LLL'],
  ['MMM d', 'd MMM'],
];

let dateLocale;

// Called when the UI language changes so dates and relative times follow it.
export const setDateLocale = code => {
  dateLocale = DATE_LOCALES[code] || DATE_LOCALES[code?.split('_')[0]];
};

const localize = pattern =>
  dateLocale
    ? DAY_FIRST_PATTERNS.reduce(
        (result, [english, dayFirst]) => result.replace(english, dayFirst),
        pattern
      )
    : pattern;

const formatLocal = (date, pattern) =>
  format(date, localize(pattern), { locale: dateLocale });

/**
 * Formats a Unix timestamp into a human-readable time format.
 * @param {number} time - Unix timestamp.
 * @param {string} [dateFormat='h:mm a'] - Desired format of the time.
 * @returns {string} Formatted time string.
 */
export const messageStamp = (time, dateFormat = 'h:mm a') => {
  const unixTime = fromUnixTime(time);
  return formatLocal(unixTime, dateFormat);
};

/**
 * Provides a formatted timestamp, adjusting the format based on the current year.
 * @param {number} time - Unix timestamp.
 * @param {string} [dateFormat='MMM d, yyyy'] - Desired date format.
 * @returns {string} Formatted date string.
 */
export const messageTimestamp = (time, dateFormat = 'MMM d, yyyy') => {
  const messageTime = fromUnixTime(time);
  const now = new Date();
  const messageDate = formatLocal(messageTime, dateFormat);
  if (!isSameYear(messageTime, now)) {
    return formatLocal(messageTime, 'LLL d y, h:mm a');
  }
  return messageDate;
};

/**
 * Formats a Unix timestamp relative to today: the time for today, a caller-
 * supplied label for yesterday, and a date otherwise. The yesterday label is
 * passed in so the caller keeps ownership of translation.
 * @param {number} time - Unix timestamp.
 * @param {string} yesterdayLabel - Localized label shown for yesterday.
 * @returns {string} Formatted timestamp string.
 */
export const relativeDayTimestamp = (time, yesterdayLabel) => {
  const date = fromUnixTime(time);
  if (isToday(date)) return formatLocal(date, 'h:mm a');
  if (isYesterday(date)) return yesterdayLabel;
  if (isThisYear(date)) return formatLocal(date, 'MMM d');
  return formatLocal(date, 'MMM d, yyyy');
};

/**
 * Converts a Unix timestamp to a relative time string (e.g., 3 hours ago).
 * @param {number} time - Unix timestamp.
 * @returns {string} Relative time string.
 */
export const dynamicTime = time => {
  const unixTime = fromUnixTime(time);
  return formatDistanceToNow(unixTime, {
    addSuffix: true,
    locale: dateLocale,
  });
};

/**
 * Formats a Unix timestamp into a specified date format.
 * @param {number} time - Unix timestamp.
 * @param {string} [dateFormat='MMM d, yyyy'] - Desired date format.
 * @returns {string} Formatted date string.
 */
export const dateFormat = (time, df = 'MMM d, yyyy') => {
  const unixTime = fromUnixTime(time);
  return formatLocal(unixTime, df);
};

/**
 * Converts a detailed time description into a shorter format, optionally appending 'ago'.
 * @param {string} time - Detailed time description (e.g., 'a minute ago').
 * @param {boolean} [withAgo=false] - Whether to append 'ago' to the result.
 * @returns {string} Shortened time description.
 */
// ServiceDesk: dynamicTime segue o idioma do painel; em pt-BR o date-fns devolve "há 4 dias", "cerca de 2 horas"...
// e o formato curto vira "4d", "2h", "5m", "1mês", "1a" (com withAgo: "há 4d").
const PT_SHORT_UNITS = [
  [/minutos?/, 'm'],
  [/horas?/, 'h'],
  [/dias?/, 'd'],
  [/m[eê]s(es)?/, 'mês'],
  [/anos?/, 'a'],
];
const shortTimestampPt = (time, withAgo) => {
  if (/menos de um minuto/.test(time)) return 'agora';
  const [count] = time.match(/\d+/) || ['1'];
  const unit = PT_SHORT_UNITS.find(([pattern]) => pattern.test(time));
  if (!unit) return time;
  const short = `${count}${unit[1]}`;
  return withAgo ? `há ${short}` : short;
};

export const shortTimestamp = (time, withAgo = false) => {
  if (/^(há|em) |menos de um minuto/.test(time)) {
    return shortTimestampPt(time, withAgo);
  }
  // This function takes a time string and converts it to a short time string
  // with the following format: 1m, 1h, 1d, 1mo, 1y
  // The function also takes an optional boolean parameter withAgo
  // which will add the word "ago" to the end of the time string
  const suffix = withAgo ? ' ago' : '';
  const timeMappings = {
    'less than a minute ago': 'now',
    'in less than a minute': 'now',
    'a minute ago': `1m${suffix}`,
    'an hour ago': `1h${suffix}`,
    'a day ago': `1d${suffix}`,
    'a month ago': `1mo${suffix}`,
    'a year ago': `1y${suffix}`,
  };
  // Check if the time string is one of the specific cases
  if (timeMappings[time]) {
    return timeMappings[time];
  }
  const convertToShortTime = time
    .replace(/about|over|almost|/g, '')
    .replace(' minute ago', `m${suffix}`)
    .replace(' minutes ago', `m${suffix}`)
    .replace(' hour ago', `h${suffix}`)
    .replace(' hours ago', `h${suffix}`)
    .replace(' day ago', `d${suffix}`)
    .replace(' days ago', `d${suffix}`)
    .replace(' month ago', `mo${suffix}`)
    .replace(' months ago', `mo${suffix}`)
    .replace(' year ago', `y${suffix}`)
    .replace(' years ago', `y${suffix}`);
  return convertToShortTime;
};

/**
 * Formats a duration in seconds into mm:ss or hh:mm:ss.
 * @param {number|string} durationInSeconds - Duration in seconds.
 * @returns {string} Formatted duration string. Empty string for invalid input.
 */
export const formatDuration = durationInSeconds => {
  if (durationInSeconds === null || durationInSeconds === undefined) return '';

  const totalSeconds = Number(durationInSeconds);
  if (Number.isNaN(totalSeconds) || totalSeconds < 0) return '';

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const mm = minutes.toString().padStart(2, '0');
  const ss = seconds.toString().padStart(2, '0');
  if (hours > 0) {
    return `${hours.toString().padStart(2, '0')}:${mm}:${ss}`;
  }
  return `${mm}:${ss}`;
};

/**
 * Calculates the difference in days between now and a given timestamp.
 * @param {Date} now - Current date/time.
 * @param {number} timestampInSeconds - Unix timestamp in seconds.
 * @returns {number} Number of days difference.
 */
export const getDayDifferenceFromNow = (now, timestampInSeconds) => {
  const date = new Date(timestampInSeconds * 1000);
  return differenceInDays(now, date);
};

/**
 * Checks if more than 24 hours have passed since a given timestamp.
 * Useful for determining if retry/refresh actions should be disabled.
 * @param {number} timestamp - Unix timestamp.
 * @returns {boolean} True if more than 24 hours have passed.
 */
export const hasOneDayPassed = timestamp => {
  if (!timestamp) return true; // Defensive check
  return getDayDifferenceFromNow(new Date(), timestamp) >= 1;
};

/**
 * Formats a Date (or date string) in the current UI language.
 * @param {Date|string} date - Date to format.
 * @param {string} pattern - date-fns pattern, written in English order.
 * @returns {string} Formatted date string.
 */
export const formatDate = (date, pattern) =>
  formatLocal(new Date(date), pattern);
