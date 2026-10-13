import {
  STATUS_CATEGORIES,
  STATUS_TOKENS,
  getStatusToken,
  CATEGORY_TO_NATIVE_STATUS,
  resolveTicketStatus,
  categoryForCustomStatus,
  getNativeStatusToken,
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

  it('follows the canonical status mapping (category -> native)', () => {
    expect(CATEGORY_TO_NATIVE_STATUS).toEqual({
      new: 'open',
      open: 'open',
      pending: 'snoozed',
      hold: 'snoozed',
      solved: 'resolved',
      closed: 'resolved',
    });
  });

  it('maps native Chatwoot statuses to categories', () => {
    expect(getStatusToken('open').category).toBe('open');
    expect(getStatusToken('snoozed').category).toBe('pending');
    expect(getStatusToken('resolved').category).toBe('solved');
    // pending nativo (bot/IA) não é usado pelo ServiceDesk: exibe Aberto
    expect(getNativeStatusToken('pending').category).toBe('open');
    expect(getNativeStatusToken('snoozed').category).toBe('pending');
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

  it('resolves the zd_status label with the color of its category', () => {
    const dev = resolveTicketStatus({
      status: 'snoozed',
      custom_attributes: { zd_status: 'Desenvolvimento Concluído' },
    });
    expect(dev.category).toBe('hold');
    expect(dev.label).toBe('Desenvolvimento Concluído');
    expect(dev.isCustom).toBe(true);
    expect(dev.token.classes.badge).toContain('bg-sd-status-hold');

    const pend = resolveTicketStatus({
      status: 'snoozed',
      zdStatus: 'Pendente',
    });
    expect(pend.category).toBe('pending');

    expect(resolveTicketStatus({ status: 'snoozed' }).category).toBe('pending');
    expect(resolveTicketStatus({ status: 'resolved' }).isCustom).toBe(false);
    expect(
      resolveTicketStatus({ status: 'open', zdStatus: 'Desconhecido' }).category
    ).toBe('open');
    expect(categoryForCustomStatus('respondido CLIENTE')).toBe('solved');
    expect(categoryForCustomStatus('Retorno Integrações ')).toBe('hold');
  });
});
