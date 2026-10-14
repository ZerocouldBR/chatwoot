// ServiceDesk: modelo do formulário da tela Telefonia 55PBX (funções puras, testadas em specs/settingsForm.spec.js).
// Os campos e tipos vêm do sd-ops (GET /admin/settings -> fields); aqui só a ordem por seção e a montagem do PUT.

export const SECTIONS = [
  {
    id: 'STATUS',
    icon: 'i-lucide-power',
    fields: ['enabled', 'chatwoot_api_token'],
  },
  {
    id: 'API',
    icon: 'i-lucide-key-round',
    fields: [
      'pbx_api_key',
      'pbx_api_key_header',
      'pbx_api_url',
      'pbx_tz_offset',
      'poll_interval_min',
      'poll_lookback_min',
    ],
  },
  {
    id: 'WEBHOOK',
    icon: 'i-lucide-webhook',
    fields: [
      'public_base_url',
      'webhook_token',
      'allowed_ips',
      'chatwoot_webhook_hmac_secret',
    ],
  },
  {
    id: 'RECORDINGS',
    icon: 'i-lucide-audio-lines',
    fields: [
      'download_recordings',
      'recordings_host',
      'audio_allowed_hosts',
      'audio_send_api_key',
      'audio_max_mb',
      'audio_bitrate',
      'chatwoot_attach_recording',
      'storage_backend',
      's3_endpoint_url',
      's3_bucket',
      's3_region',
      's3_access_key_id',
      's3_secret_access_key',
      'raw_retention_days',
    ],
  },
  {
    id: 'DIAL',
    icon: 'i-lucide-phone-outgoing',
    fields: [
      'dial_mode',
      'dial_url',
      'dial_client_code',
      'dial_api_key',
      'dial_jwt',
      'dial_timeout_s',
      'webphone_url',
    ],
  },
  {
    id: 'URA',
    icon: 'i-lucide-list-tree',
    fields: [
      'ura_auth_type',
      'ura_header',
      'ura_token',
      'ura_user',
      'ura_password',
      'ura_require_caller_match',
      'ura_rate_limit_per_min',
    ],
  },
  {
    id: 'MAPS',
    icon: 'i-lucide-git-fork',
    fields: [
      'queue_team_map',
      'branch_team_map',
      'team_area_map',
      'default_team',
      'agent_match_by_name',
    ],
  },
  { id: 'TICKETS', icon: 'i-lucide-ticket', fields: [] },
  { id: 'HOURS', icon: 'i-lucide-clock', fields: [] },
  {
    id: 'N8N',
    icon: 'i-lucide-workflow',
    fields: ['n8n_base_url', 'n8n_hmac_secret', 'n8n_webhook_token'],
  },
];

// campo só aparece quando faz sentido (ex. S3 só com storage s3)
export function isFieldVisible(key, values) {
  if (key.startsWith('s3_')) return values.storage_backend === 's3';
  if (key === 'ura_header') return values.ura_auth_type === 'token';
  if (key === 'ura_token') return values.ura_auth_type !== 'basic';
  if (key === 'ura_user' || key === 'ura_password')
    return values.ura_auth_type === 'basic';
  return true;
}

const clone = v => JSON.parse(JSON.stringify(v ?? null));

// estado inicial do formulário a partir do GET
export function formFromSettings(data) {
  const values = {};
  const secrets = {};
  Object.entries(data.fields || {}).forEach(([key, meta]) => {
    if (meta.kind === 'secret') secrets[key] = { value: '', clear: false };
    else values[key] = clone(meta.value);
  });
  return {
    values,
    secrets,
    resets: {},
    agentMappings: clone(data.agent_mappings || []),
    ticketOpenRules: clone(data.ticket_open_rules || []),
    businessHours: clone(data.business_hours || null),
    slaPolicies: clone(data.sla_policies || []),
  };
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// PUT parcial: só o que mudou. Segredo vazio = manter; "apagar" = null (volta ao ambiente).
export function buildPayload(data, form) {
  const initial = formFromSettings(data);
  const payload = { version: data.version, values: {}, secrets: {} };
  Object.entries(form.values).forEach(([key, value]) => {
    if (form.resets[key]) payload.values[key] = null;
    else if (!same(value, initial.values[key])) payload.values[key] = value;
  });
  Object.entries(form.secrets).forEach(([key, s]) => {
    if (s.clear) payload.secrets[key] = null;
    else if (s.value) payload.secrets[key] = s.value;
  });
  if (!same(form.agentMappings, initial.agentMappings))
    payload.agent_mappings = form.agentMappings.filter(
      m => m.branch && m.agent_email
    );
  if (!same(form.ticketOpenRules, initial.ticketOpenRules))
    payload.ticket_open_rules = form.ticketOpenRules;
  if (!same(form.businessHours, initial.businessHours))
    payload.business_hours = form.businessHours;
  if (!same(form.slaPolicies, initial.slaPolicies))
    payload.sla_policies = form.slaPolicies;
  return payload;
}

export function isPayloadEmpty(payload) {
  return (
    !Object.keys(payload.values).length &&
    !Object.keys(payload.secrets).length &&
    !payload.agent_mappings &&
    !payload.ticket_open_rules &&
    !payload.business_hours &&
    !payload.sla_policies
  );
}

// mapa {chave: valor} <-> linhas editáveis
export const mapToRows = map =>
  Object.entries(map || {}).map(([key, value]) => ({ key, value }));
export const rowsToMap = rows =>
  Object.fromEntries(
    rows
      .filter(r => (r.key || '').trim() && (r.value || '').trim())
      .map(r => [r.key.trim(), r.value.trim()])
  );

// lista (IPs, hosts) <-> texto separado por vírgula
export const listToText = list =>
  Array.isArray(list) ? list.join(', ') : String(list ?? '');
export const textToList = text =>
  (text || '')
    .split(/[,;\n]/)
    .map(s => s.trim())
    .filter(Boolean);
