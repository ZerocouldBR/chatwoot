import {
  dynamicTime,
  setDateLocale,
  shortTimestamp,
} from 'shared/helpers/timeHelper';

// ServiceDesk: com o painel em pt-BR, dynamicTime devolve "há 4 dias"; a lista de tickets mostra a forma curta.
describe('shortTimestamp em pt-BR', () => {
  beforeEach(() => {
    process.env.TZ = 'UTC';
    vi.useFakeTimers('modern');
    vi.setSystemTime(new Date(Date.UTC(2023, 4, 5, 12)));
    setDateLocale('pt_BR');
  });

  afterEach(() => {
    setDateLocale('en');
    vi.useRealTimers();
  });

  const ago = seconds => Date.UTC(2023, 4, 5, 12) / 1000 - seconds;

  it('encurta minutos, horas, dias, meses e anos', () => {
    expect(shortTimestamp(dynamicTime(ago(10)))).toBe('agora');
    expect(shortTimestamp(dynamicTime(ago(5 * 60)))).toBe('5m');
    expect(shortTimestamp(dynamicTime(ago(2 * 3600)))).toBe('2h');
    expect(shortTimestamp(dynamicTime(ago(4 * 86400)))).toBe('4d');
    expect(shortTimestamp(dynamicTime(ago(65 * 86400)))).toBe('2mês');
    expect(shortTimestamp(dynamicTime(ago(800 * 86400)))).toBe('2a');
  });

  it('com withAgo mantém o "há"', () => {
    expect(shortTimestamp(dynamicTime(ago(4 * 86400)), true)).toBe('há 4d');
  });

  it('em inglês continua igual ao upstream', () => {
    setDateLocale('en');
    expect(shortTimestamp(dynamicTime(ago(4 * 86400)))).toBe('4d');
  });
});
