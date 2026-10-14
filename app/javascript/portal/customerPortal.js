// ServiceDesk B2B: comportamento das telas do portal do cliente (login, "Enviar uma solicitação",
// "Minhas solicitações" e resposta no ticket). O servidor valida tudo de novo; aqui só melhora a experiência.

const BLOCKED_TYPES = [
  'image/svg+xml',
  'text/html',
  'application/xhtml+xml',
  'application/javascript',
  'text/javascript',
];

export const formatFileSize = bytes => {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`;
};

// Devolve a lista de problemas dos arquivos escolhidos (vazia = ok).
export const validateFiles = (files, { maxFiles, maxBytes }) => {
  const list = Array.from(files || []);
  const errors = [];
  if (maxFiles && list.length > maxFiles) {
    errors.push({ code: 'too_many', limit: maxFiles });
  }
  list.forEach(file => {
    if (maxBytes && file.size > maxBytes) {
      errors.push({ code: 'too_big', file: file.name });
    }
    if (BLOCKED_TYPES.includes(file.type)) {
      errors.push({ code: 'type', file: file.name });
    }
  });
  return errors;
};

const ERROR_TEXT = {
  pt: {
    too_many: ({ limit }) => `Envie no máximo ${limit} anexos.`,
    too_big: ({ file }) => `O arquivo ${file} passa do limite.`,
    type: ({ file }) => `O tipo do arquivo ${file} não é aceito.`,
  },
  en: {
    too_many: ({ limit }) => `Send at most ${limit} attachments.`,
    too_big: ({ file }) => `The file ${file} exceeds the limit.`,
    type: ({ file }) => `The file type of ${file} is not supported.`,
  },
};

export const describeFileErrors = (errors, locale = 'pt_BR') => {
  const texts = String(locale).startsWith('pt') ? ERROR_TEXT.pt : ERROR_TEXT.en;
  return errors.map(error => texts[error.code](error)).join(' ');
};

const setSubmitDisabled = (form, disabled) => {
  if (!form) return;
  form
    .querySelectorAll('button[type="submit"], input[type="submit"]')
    .forEach(button => button.toggleAttribute('disabled', disabled));
};

export const initAttachmentInputs = (root = document) => {
  root
    .querySelectorAll('input[type="file"][data-sd-attachments]')
    .forEach(input => {
      if (input.dataset.sdBound) return;
      input.dataset.sdBound = 'true';
      const container = input.closest('.sd-files') || input.parentElement;
      const listEl = container.querySelector('[data-sd-attachments-list]');
      const errorEl = container.querySelector('[data-sd-attachments-error]');

      input.addEventListener('change', () => {
        const files = Array.from(input.files || []);
        if (listEl) {
          listEl.replaceChildren(
            ...files.map(file => {
              const item = document.createElement('li');
              const name = document.createElement('span');
              name.textContent = file.name;
              const size = document.createElement('span');
              size.textContent = formatFileSize(file.size);
              item.append(name, size);
              return item;
            })
          );
        }
        const errors = validateFiles(files, {
          maxFiles: Number(input.dataset.maxFiles) || 0,
          maxBytes: Number(input.dataset.maxBytes) || 0,
        });
        const locale = window.portalConfig?.localeCode || 'pt_BR';
        if (errorEl) {
          errorEl.textContent = describeFileErrors(errors, locale);
          errorEl.hidden = errors.length === 0;
        }
        setSubmitDisabled(input.form, errors.length > 0);
      });
    });
};

// Evita envio duplicado (duplo clique cria dois tickets).
export const initSubmitOnce = (root = document) => {
  root.querySelectorAll('form[data-sd-submit-once]').forEach(form => {
    if (form.dataset.sdBound) return;
    form.dataset.sdBound = 'true';
    form.addEventListener('submit', event => {
      if (form.dataset.sdSubmitting === 'true') {
        event.preventDefault();
        return;
      }
      form.dataset.sdSubmitting = 'true';
      setSubmitDisabled(form, true);
    });
  });
};

export const buildFormSwitchUrl = (baseUrl, formId, origin) => {
  const url = new URL(baseUrl, origin);
  url.searchParams.set('form', formId);
  return url.pathname + url.search;
};

export const initFormSwitcher = (root = document) => {
  root.querySelectorAll('select[data-sd-form-switcher]').forEach(select => {
    select.addEventListener('change', () => {
      window.location.href = buildFormSwitchUrl(
        select.dataset.sdFormSwitcher,
        select.value,
        window.location.origin
      );
    });
  });
  root.querySelectorAll('select[data-sd-autosubmit]').forEach(select => {
    select.addEventListener('change', () => select.form?.submit());
  });
};

export const initCustomerPortal = (root = document) => {
  if (
    !root.querySelector(
      '.sd-b2b, [data-sd-attachments], form[data-sd-submit-once]'
    )
  ) {
    return;
  }
  initAttachmentInputs(root);
  initSubmitOnce(root);
  initFormSwitcher(root);
};
