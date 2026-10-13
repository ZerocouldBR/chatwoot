import {
  getTicketHeaderStatus,
  getTicketHeaderTitle,
  getTicketSubject,
} from '../ticketHeader';

describe('ticketHeader', () => {
  it('usa o assunto do e-mail como título', () => {
    const chat = {
      additional_attributes: { mail_subject: '  Erro   no checkout ' },
    };
    expect(getTicketSubject(chat)).toBe('Erro no checkout');
    expect(getTicketHeaderTitle(chat, 'Heitor')).toEqual({
      title: 'Erro no checkout',
      hasSubject: true,
    });
  });

  it('usa zd_assunto quando não há mail_subject (tickets importados)', () => {
    const chat = { custom_attributes: { zd_assunto: 'Reserva duplicada' } };
    expect(getTicketHeaderTitle(chat, 'Heitor').title).toBe(
      'Reserva duplicada'
    );
  });

  it('cai para o nome do contato sem assunto', () => {
    expect(getTicketHeaderTitle({}, 'Heitor Protótipo')).toEqual({
      title: 'Heitor Protótipo',
      hasSubject: false,
    });
    expect(getTicketHeaderTitle(undefined, undefined).title).toBe('');
  });

  it('selo mostra o rótulo zd_status com a categoria', () => {
    const status = getTicketHeaderStatus({
      status: 'snoozed',
      custom_attributes: { zd_status: 'Desenvolvimento Concluído' },
    });
    expect(status.label).toBe('Desenvolvimento Concluído');
    expect(status.category).toBe('hold');
    expect(status.token.classes.badge).toContain('bg-sd-status-hold');
  });

  it('sem zd_status, snoozed aparece como Pendente (status canônico)', () => {
    const status = getTicketHeaderStatus({ status: 'snoozed' });
    expect(status.label).toBe('');
    expect(status.category).toBe('pending');
  });
});
