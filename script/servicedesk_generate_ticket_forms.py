#!/usr/bin/env python3
"""Gera os JSONs estaticos de formularios de ticket do ServiceDesk.

Fonte: export de configuracao do Zendesk (ticket_forms.json, ticket_fields.json,
custom_statuses.json). Saida (versionada no fork):

  app/javascript/dashboard/servicedesk/ticketForms.json
      { "<nome do formulario>": [<zendesk_field_id em ordem>, ...] }
  app/javascript/dashboard/servicedesk/ticketFormsMeta.json
      formulario padrao, ids/posicao/ativo de cada formulario, condicoes
      (campos condicionais, com o valor do pai convertido para o NOME da opcao,
      que e o que fica gravado no atributo do ServiceDesk), campos
      obrigatorios para resolver e categoria de cada status personalizado.

Fonte provisoria: o modulo M1 leva estas informacoes para o banco.

Uso:
  python3 script/servicedesk_generate_ticket_forms.py <dir_config_zendesk> <dir_saida>
"""
import json
import os
import sys


def load(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else '/opt/servicedesk-data/zendesk-config'
    out = sys.argv[2] if len(sys.argv) > 2 else 'app/javascript/dashboard/servicedesk'
    forms = load(os.path.join(src, 'ticket_forms.json'))
    fields = {f['id']: f for f in load(os.path.join(src, 'ticket_fields.json'))}
    statuses = load(os.path.join(src, 'custom_statuses.json'))

    forms = sorted(forms, key=lambda f: (f.get('position') or 0, f['id']))

    def option_name(field_id, value):
        field = fields.get(field_id) or {}
        for opt in field.get('custom_field_options') or []:
            if opt.get('value') == value:
                return opt.get('name')
        if field.get('type') == 'checkbox':
            return value
        return value

    ticket_forms = {}
    meta_forms = {}
    conditions = {}
    default_form = None
    for form in forms:
        name = form['name'].strip()
        ticket_forms[name] = list(form['ticket_field_ids'])
        meta_forms[name] = {
            'id': form['id'],
            'position': form.get('position'),
            'active': bool(form.get('active')),
            'default': bool(form.get('default')),
        }
        if form.get('default') and form.get('active'):
            default_form = name
        conds = []
        for cond in form.get('agent_conditions') or []:
            parent = cond['parent_field_id']
            conds.append({
                'parent_field_id': parent,
                'value': option_name(parent, cond['value']),
                'value_tag': cond['value'],
                'child_fields': [
                    {
                        'id': child['id'],
                        'is_required': bool(child.get('is_required')),
                    }
                    for child in cond.get('child_fields') or []
                ],
            })
        conditions[name] = conds

    if default_form is None:
        default_form = next(iter(ticket_forms), None)

    required = sorted(
        fid for fid, f in fields.items()
        if f.get('required') and f.get('active') and f.get('type') not in ('assignee',)
    )

    # STATUS NATIVO da v3 (enum do Victor, igual ao Zendesk; o rotulo exato fica em zd_status).
    # O status nativo "pending" do Chatwoot fica reservado a bot/IA e nunca e usado aqui.
    category_to_native = {
        'new': 'new_ticket', 'open': 'open', 'pending': 'waiting_on_customer',
        'hold': 'on_hold', 'solved': 'resolved', 'closed': 'closed',
    }
    status_meta = {}
    native_default = {}
    for st in statuses:
        label = st['agent_label'].strip()
        status_meta[label] = {
            'id': st['id'],
            'category': st['status_category'],
            'native': category_to_native.get(st['status_category'], 'open'),
            'active': bool(st.get('active')),
        }
        if st.get('default') and st.get('active'):
            native = category_to_native.get(st['status_category'])
            # um status nativo por categoria (v3): o padrao de cada um e o default da categoria.
            if native and st['status_category'] in ('open', 'pending', 'hold', 'solved'):
                native_default[native] = label

    meta = {
        '_source': 'zendesk-config: ticket_forms.json, ticket_fields.json, custom_statuses.json',
        'default_form': default_form,
        'forms': meta_forms,
        'conditions': conditions,
        'required_field_ids': required,
        'statuses': status_meta,
        'native_status_default': native_default,
    }

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'ticketForms.json'), 'w', encoding='utf-8') as fh:
        json.dump(ticket_forms, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    with open(os.path.join(out, 'ticketFormsMeta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    print('OK forms=%d default=%s' % (len(ticket_forms), default_form))


if __name__ == '__main__':
    main()
