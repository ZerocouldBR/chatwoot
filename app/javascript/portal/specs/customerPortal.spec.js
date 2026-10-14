import {
  formatFileSize,
  validateFiles,
  describeFileErrors,
  buildFormSwitchUrl,
  initAttachmentInputs,
  initSubmitOnce,
  initCustomerPortal,
} from '../customerPortal';

const fakeFile = (name, size, type = 'application/pdf') => ({
  name,
  size,
  type,
});

describe('customerPortal (portal do cliente B2B)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.className = '';
    window.portalConfig = { localeCode: 'pt_BR' };
  });

  describe('formatFileSize', () => {
    it('formata bytes, KB e MB', () => {
      expect(formatFileSize(512)).toBe('512 B');
      expect(formatFileSize(2048)).toBe('2 KB');
      expect(formatFileSize(5 * 1024 * 1024)).toBe('5,0 MB');
      expect(formatFileSize(undefined)).toBe('0 B');
    });
  });

  describe('validateFiles', () => {
    it('aceita arquivos dentro dos limites', () => {
      expect(
        validateFiles([fakeFile('boleto.pdf', 100)], {
          maxFiles: 10,
          maxBytes: 1000,
        })
      ).toEqual([]);
    });

    it('recusa excesso de arquivos, arquivo grande e SVG/HTML', () => {
      const files = [
        fakeFile('a.pdf', 10),
        fakeFile('grande.zip', 5000, 'application/zip'),
        fakeFile('logo.svg', 10, 'image/svg+xml'),
        fakeFile('pagina.html', 10, 'text/html'),
      ];
      const errors = validateFiles(files, { maxFiles: 3, maxBytes: 1000 });
      expect(errors).toEqual([
        { code: 'too_many', limit: 3 },
        { code: 'too_big', file: 'grande.zip' },
        { code: 'type', file: 'logo.svg' },
        { code: 'type', file: 'pagina.html' },
      ]);
    });

    it('descreve os erros em português e em inglês', () => {
      const errors = [
        { code: 'too_many', limit: 2 },
        { code: 'type', file: 'x.svg' },
      ];
      expect(describeFileErrors(errors, 'pt_BR')).toBe(
        'Envie no máximo 2 anexos. O tipo do arquivo x.svg não é aceito.'
      );
      expect(describeFileErrors(errors, 'en')).toBe(
        'Send at most 2 attachments. The file type of x.svg is not supported.'
      );
    });
  });

  it('monta a URL de troca de formulário preservando o caminho', () => {
    expect(
      buildFormSwitchUrl(
        '/hc/central-b2b/pt_BR/requests/new',
        'atendimento',
        'https://helpdesk.example'
      )
    ).toBe('/hc/central-b2b/pt_BR/requests/new?form=atendimento');
  });

  describe('initAttachmentInputs', () => {
    const mount = () => {
      document.body.innerHTML = `
        <form>
          <div class="sd-files">
            <input type="file" data-sd-attachments data-max-files="2" data-max-bytes="1000">
            <ul data-sd-attachments-list></ul>
            <p data-sd-attachments-error hidden></p>
          </div>
          <button type="submit">Enviar</button>
        </form>`;
      initAttachmentInputs(document);
      return document.querySelector('input[type="file"]');
    };

    const choose = (input, files) => {
      Object.defineProperty(input, 'files', {
        value: files,
        configurable: true,
      });
      input.dispatchEvent(new Event('change'));
    };

    it('lista os arquivos escolhidos com o tamanho', () => {
      const input = mount();
      choose(input, [fakeFile('nota.pdf', 2048 / 4)]);
      const items = document.querySelectorAll('[data-sd-attachments-list] li');
      expect(items).toHaveLength(1);
      expect(items[0].textContent).toContain('nota.pdf');
      expect(document.querySelector('[data-sd-attachments-error]').hidden).toBe(
        true
      );
      expect(document.querySelector('button').hasAttribute('disabled')).toBe(
        false
      );
    });

    it('mostra o erro e bloqueia o envio quando passa do limite', () => {
      const input = mount();
      choose(input, [fakeFile('enorme.pdf', 5000)]);
      const error = document.querySelector('[data-sd-attachments-error]');
      expect(error.hidden).toBe(false);
      expect(error.textContent).toContain('enorme.pdf');
      expect(document.querySelector('button').hasAttribute('disabled')).toBe(
        true
      );

      choose(input, [fakeFile('ok.pdf', 10)]);
      expect(error.hidden).toBe(true);
      expect(document.querySelector('button').hasAttribute('disabled')).toBe(
        false
      );
    });
  });

  it('initSubmitOnce também desabilita input[type=submit] (formulários do tema Copenhagen)', () => {
    document.body.innerHTML = `
      <form data-sd-submit-once><input type="submit" value="Enviar"></form>`;
    initSubmitOnce(document);
    document
      .querySelector('form')
      .dispatchEvent(new Event('submit', { cancelable: true }));
    expect(
      document.querySelector('input[type="submit"]').hasAttribute('disabled')
    ).toBe(true);
  });

  it('initSubmitOnce impede o segundo envio do formulário', () => {
    document.body.innerHTML = `
      <form data-sd-submit-once><button type="submit">Enviar</button></form>`;
    initSubmitOnce(document);
    const form = document.querySelector('form');
    const first = new Event('submit', { cancelable: true });
    form.dispatchEvent(first);
    expect(first.defaultPrevented).toBe(false);
    expect(form.querySelector('button').hasAttribute('disabled')).toBe(true);

    const second = new Event('submit', { cancelable: true });
    form.dispatchEvent(second);
    expect(second.defaultPrevented).toBe(true);
  });

  it('initCustomerPortal não faz nada fora do tema B2B', () => {
    document.body.innerHTML = '<form><button type="submit">x</button></form>';
    expect(() => initCustomerPortal(document)).not.toThrow();
    expect(document.querySelector('form').dataset.sdBound).toBeUndefined();
  });
});
