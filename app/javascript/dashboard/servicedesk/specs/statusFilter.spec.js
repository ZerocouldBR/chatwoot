import {
  SD_STATUS_FILTER,
  SD_STATUS_FILTER_OPTIONS,
  isSdCategoryFilter,
  matchesStatusFilter,
  toApiStatusParams,
  toNativeStatus,
} from '../statusFilter';
import {
  applyPageFilters,
  filterByStatus,
} from 'dashboard/store/modules/conversations/helpers';

const ticket = (status, zdStatus) => ({
  id: 1,
  status,
  custom_attributes: zdStatus ? { zd_status: zdStatus } : {},
  meta: {},
  labels: [],
});

describe('statusFilter', () => {
  it('lista Aberto, Pendente, Em espera, Resolvido e Todos nessa ordem', () => {
    expect(SD_STATUS_FILTER_OPTIONS).toEqual([
      'open',
      'sd_pending',
      'sd_hold',
      'resolved',
      'all',
    ]);
  });

  it('converte Pendente/Em espera para snoozed + categoria na API', () => {
    expect(toApiStatusParams(SD_STATUS_FILTER.PENDING)).toEqual({
      status: 'snoozed',
      zd_status_category: 'pending',
    });
    expect(toApiStatusParams(SD_STATUS_FILTER.HOLD)).toEqual({
      status: 'snoozed',
      zd_status_category: 'hold',
    });
    expect(toApiStatusParams('open')).toEqual({ status: 'open' });
    expect(toApiStatusParams(undefined)).toEqual({ status: undefined });
  });

  it('mapeia para o status nativo (modal de filtros)', () => {
    expect(toNativeStatus('sd_hold')).toBe('snoozed');
    expect(toNativeStatus('sd_pending')).toBe('snoozed');
    expect(toNativeStatus('resolved')).toBe('resolved');
    expect(isSdCategoryFilter('snoozed')).toBe(false);
  });

  describe('matchesStatusFilter', () => {
    it('Em espera = snoozed com zd_status de categoria hold', () => {
      expect(
        matchesStatusFilter(ticket('snoozed', 'Desenvolvimento'), 'sd_hold')
      ).toBe(true);
      expect(
        matchesStatusFilter(
          ticket('snoozed', 'desenvolvimento concluido'),
          'sd_hold'
        )
      ).toBe(true);
      expect(
        matchesStatusFilter(ticket('snoozed', 'Pendente'), 'sd_hold')
      ).toBe(false);
      expect(
        matchesStatusFilter(ticket('open', 'Desenvolvimento'), 'sd_hold')
      ).toBe(false);
    });

    it('Pendente = demais snoozed (categoria pending ou sem rótulo)', () => {
      expect(
        matchesStatusFilter(ticket('snoozed', 'Pendente'), 'sd_pending')
      ).toBe(true);
      expect(matchesStatusFilter(ticket('snoozed'), 'sd_pending')).toBe(true);
      expect(
        matchesStatusFilter(ticket('snoozed', 'Devolvido'), 'sd_pending')
      ).toBe(false);
      expect(matchesStatusFilter(ticket('resolved'), 'sd_pending')).toBe(false);
    });

    it('status nativos e Todos continuam iguais', () => {
      expect(matchesStatusFilter(ticket('open'), 'open')).toBe(true);
      expect(matchesStatusFilter(ticket('open'), 'resolved')).toBe(false);
      expect(matchesStatusFilter(ticket('resolved'), 'all')).toBe(true);
    });
  });

  it('o store usa o mesmo critério nas atualizações em tempo real', () => {
    const hold = ticket('snoozed', 'Devolvido');
    expect(applyPageFilters(hold, { status: 'sd_hold' })).toBe(true);
    expect(applyPageFilters(hold, { status: 'sd_pending' })).toBe(false);
    expect(applyPageFilters(hold, { status: 'snoozed' })).toBe(true);
    expect(filterByStatus('open', 'open')).toBe(true);
    expect(filterByStatus('open', 'all')).toBe(true);
  });
});
