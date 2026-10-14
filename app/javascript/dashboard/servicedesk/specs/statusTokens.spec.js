import {
  STATUS_CATEGORIES,
  CATEGORY_TO_NATIVE_STATUS,
  categoryForCustomStatus,
} from '../statusTokens';

describe('servicedesk statusTokens', () => {
  it('maps every category to a ticket status agents can set', () => {
    expect(CATEGORY_TO_NATIVE_STATUS).toEqual({
      new: 'open',
      open: 'open',
      pending: 'waiting_on_customer',
      hold: 'on_hold',
      solved: 'resolved',
      closed: 'resolved',
    });
    STATUS_CATEGORIES.forEach(category =>
      expect(CATEGORY_TO_NATIVE_STATUS[category]).toBeTruthy()
    );
  });

  it('finds the category of a custom status, ignoring case and accents', () => {
    expect(categoryForCustomStatus('Desenvolvimento Concluído')).toBe('hold');
    expect(categoryForCustomStatus('em andamento')).toBe('open');
    expect(categoryForCustomStatus('Inexistente')).toBeNull();
  });
});
