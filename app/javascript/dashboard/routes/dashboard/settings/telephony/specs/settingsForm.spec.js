import {
  buildPayload,
  formFromSettings,
  isFieldVisible,
  isPayloadEmpty,
  rowsToMap,
  mapToRows,
  textToList,
} from '../settingsForm';
import { settingsFixture } from './fixtures';

describe('settingsForm (Telefonia 55PBX)', () => {
  it('sem alteração não envia nada e nunca carrega segredo no formulário', () => {
    const data = settingsFixture();
    const form = formFromSettings(data);
    expect(form.secrets.pbx_api_key).toEqual({ value: '', clear: false });
    expect(form.values.pbx_api_key).toBeUndefined();
    const payload = buildPayload(data, form);
    expect(payload.version).toBe(3);
    expect(isPayloadEmpty(payload)).toBe(true);
  });

  it('envia só o que mudou; segredo vazio mantém, "apagar" vira null e "voltar ao ambiente" também', () => {
    const data = settingsFixture();
    const form = formFromSettings(data);
    form.values.poll_interval_min = 5;
    form.values.queue_team_map = { fila_suporte_1: 'Financeiro' };
    form.secrets.dial_jwt.value = 'jwt-novo';
    form.secrets.pbx_api_key.clear = true;
    form.resets.dial_mode = true;
    const payload = buildPayload(data, form);
    expect(payload.values).toEqual({
      poll_interval_min: 5,
      queue_team_map: { fila_suporte_1: 'Financeiro' },
      dial_mode: null,
    });
    expect(payload.secrets).toEqual({
      dial_jwt: 'jwt-novo',
      pbx_api_key: null,
    });
    expect(payload.agent_mappings).toBeUndefined();
  });

  it('tabelas (ramais, regras, horário, SLA) só vão quando editadas', () => {
    const data = settingsFixture();
    const form = formFromSettings(data);
    form.agentMappings.push({
      branch: '5010',
      agent_email: 'bruno@exemplo.test',
      chatwoot_user_id: 12,
    });
    form.agentMappings.push({ branch: '', agent_email: '' });
    form.slaPolicies[0].first_response_min = 60;
    const payload = buildPayload(data, form);
    expect(payload.agent_mappings.map(m => m.branch)).toEqual(['5005', '5010']);
    expect(payload.sla_policies[0].first_response_min).toBe(60);
    expect(payload.ticket_open_rules).toBeUndefined();
    expect(payload.business_hours).toBeUndefined();
  });

  it('campos condicionais, mapas e listas', () => {
    expect(isFieldVisible('s3_bucket', { storage_backend: 'local' })).toBe(
      false
    );
    expect(isFieldVisible('s3_bucket', { storage_backend: 's3' })).toBe(true);
    expect(isFieldVisible('ura_user', { ura_auth_type: 'token' })).toBe(false);
    expect(isFieldVisible('ura_password', { ura_auth_type: 'basic' })).toBe(
      true
    );
    expect(
      rowsToMap([
        { key: ' a ', value: 'b' },
        { key: '', value: 'x' },
      ])
    ).toEqual({ a: 'b' });
    expect(mapToRows({ a: 'b' })).toEqual([{ key: 'a', value: 'b' }]);
    expect(textToList('10.0.0.0/8, 192.168.0.1;\n')).toEqual([
      '10.0.0.0/8',
      '192.168.0.1',
    ]);
  });
});
