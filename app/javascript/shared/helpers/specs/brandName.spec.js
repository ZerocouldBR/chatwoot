import { brandMessages, getBrandName, replaceBrandName } from '../brandName';

describe('brandName', () => {
  afterEach(() => {
    window.globalConfig = undefined;
  });

  it('uses the installation name when configured', () => {
    window.globalConfig = { INSTALLATION_NAME: 'Acme Desk' };
    expect(getBrandName()).toBe('Acme Desk');
    expect(replaceBrandName('Welcome to Chatwoot')).toBe(
      'Welcome to Acme Desk'
    );
  });

  it('falls back to a neutral name', () => {
    expect(getBrandName()).toBe('ServiceDesk');
  });

  it('rewrites nested message templates without touching placeholders', () => {
    window.globalConfig = { INSTALLATION_NAME: 'Acme Desk' };
    const messages = {
      en: {
        TITLE: 'Login to Chatwoot',
        LINK: 'Open {url}',
        LIST: ['chatwoot'],
      },
    };
    expect(brandMessages(messages)).toEqual({
      en: {
        TITLE: 'Login to Acme Desk',
        LINK: 'Open {url}',
        LIST: ['Acme Desk'],
      },
    });
  });

  it('keeps domains, paths, e-mails and placeholders intact', () => {
    window.globalConfig = { INSTALLATION_NAME: 'Acme Desk' };
    expect(
      replaceBrandName(
        'Chatwoot: https://www.chatwoot.com/terms, chatwoot/chatwoot, a@chatwoot.com, {latestChatwootVersion}. Chatwoot.'
      )
    ).toBe(
      'Acme Desk: https://www.chatwoot.com/terms, chatwoot/chatwoot, a@chatwoot.com, {latestChatwootVersion}. Acme Desk.'
    );
  });
});
