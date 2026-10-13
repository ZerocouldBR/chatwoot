import {
  STATUS_CATEGORIES,
  STATUS_TOKENS,
  getStatusToken,
  CATEGORY_TO_NATIVE_STATUS,
} from '../statusTokens';
import en from '../../i18n/locale/en/sdTheme.json';
import ptBR from '../../i18n/locale/pt_BR/sdTheme.json';

describe('servicedesk statusTokens', () => {
  it('exposes a token for every category', () => {
    STATUS_CATEGORIES.forEach(category => {
      const token = STATUS_TOKENS[category];
      expect(token.category).toBe(category);
      expect(token.classes.badge).toBe(
        `bg-sd-status-${category} text-sd-status-${category}-fg`
      );
      expect(token.cssVar.bg).toBe(`--sd-status-${category}`);
      expect(token.hex.bg).toMatch(/^#[0-9A-F]{6}$/);
      expect(CATEGORY_TO_NATIVE_STATUS[category]).toBeTruthy();
    });
  });

  it('maps native Chatwoot statuses to Zendesk-like categories', () => {
    expect(getStatusToken('open').category).toBe('open');
    expect(getStatusToken('pending').category).toBe('pending');
    expect(getStatusToken('snoozed').category).toBe('hold');
    expect(getStatusToken('resolved').category).toBe('solved');
    expect(getStatusToken('NEW').category).toBe('new');
    expect(getStatusToken(undefined).category).toBe('open');
  });

  it('has labels for every category in en and pt_BR', () => {
    STATUS_CATEGORIES.forEach(category => {
      const key = category.toUpperCase();
      expect(en.SD_THEME.STATUS[key]).toBeTruthy();
      expect(ptBR.SD_THEME.STATUS[key]).toBeTruthy();
      expect(ptBR.SD_THEME.STATUS_SHORT[key]).toBeTruthy();
    });
    expect(ptBR.SD_THEME.STATUS.HOLD).toBe('Em espera');
  });
});
