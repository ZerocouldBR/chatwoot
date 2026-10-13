const DEFAULT_BRAND_NAME = 'Helpdesk';
const BRAND_PATTERN = /chatwoot/gi;

export const getBrandName = () =>
  window.globalConfig?.INSTALLATION_NAME || DEFAULT_BRAND_NAME;

export const replaceBrandName = text => {
  if (typeof text !== 'string') return text;
  return text.replace(BRAND_PATTERN, getBrandName());
};

// Translations ship with the upstream product name baked in. Rewrite the
// message templates (before interpolation, so dynamic values are untouched)
// to use the installation name instead.
export const brandMessages = messages => {
  if (typeof messages === 'string') return replaceBrandName(messages);
  if (Array.isArray(messages)) return messages.map(brandMessages);
  if (messages && typeof messages === 'object') {
    return Object.fromEntries(
      Object.entries(messages).map(([key, value]) => [
        key,
        brandMessages(value),
      ])
    );
  }
  return messages;
};
