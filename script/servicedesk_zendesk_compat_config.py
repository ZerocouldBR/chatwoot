#!/usr/bin/env python3
"""Gera config/servicedesk/zendesk_compat.json (camada de compatibilidade com a API do Zendesk, M7).

Fonte: provisioning/zendesk_field_map.json (mapa da importação, gerado pelo gen_map.py a partir da
configuração do Zendesk). Só entra o que a API de compatibilidade precisa para traduzir os dados:

  ticket_fields   id do campo no Zendesk -> atributo zd_* (o vínculo de verdade fica no banco, na descrição
                  "zendesk_field:<id>" da definição do atributo; aqui ficam tipo, título e as opções tag -> nome,
                  que o banco não guarda porque os atributos de lista gravam o NOME da opção)
  groups          id do grupo no Zendesk -> nome do time
  via_channels    via.channel do Zendesk -> rótulo de zd_canal
  priorities / types / custom_statuses (rótulo para o cliente e status padrão de cada categoria)
  user_fields / org_fields   chave do campo no Zendesk -> atributo zd_* e opções

Nenhum dado de cliente entra no arquivo (só a estrutura da conta).

Uso:
  python3 script/servicedesk_zendesk_compat_config.py <zendesk_field_map.json> > config/servicedesk/zendesk_compat.json
"""
import json
import sys


def options_list(options):
    return [[tag, name] for tag, name in (options or {}).items()]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'provisioning/zendesk_field_map.json'
    with open(src, encoding='utf-8') as fh:
        fmap = json.load(fh)

    fields = []
    for zid, f in sorted(fmap['ticket_fields'].items(), key=lambda kv: (kv[1].get('position') or 0, int(kv[0]))):
        fields.append({
            'id': int(zid),
            'title': f.get('title'),
            'zendesk_type': f.get('zendesk_type'),
            'type': f.get('type'),
            'key': f.get('key'),
            'system': bool(f.get('system')),
            'active': bool(f.get('active')),
            'position': f.get('position'),
            'required': bool(f.get('required_agent')),
            'required_in_portal': bool(f.get('required_in_portal')),
            'visible_in_portal': bool(f.get('visible_in_portal')),
            'description': f.get('description'),
            'tag': f.get('tag'),
            'options': options_list(f.get('options')),
            'historical_options': options_list(f.get('historical_options')),
        })

    groups = {zid: {'name': d.get('zendesk_name') or fmap['groups'].get(zid), 'team_name': d.get('team_name'),
                    'deleted': bool(d.get('deleted'))}
              for zid, d in fmap.get('groups_detail', {}).items()}

    system = fmap['system']
    statuses = {zid: {'label': s['label'], 'end_user_label': s.get('end_user_label'), 'category': s['category'],
                      'active': bool(s.get('active')), 'default': bool(s.get('default'))}
                for zid, s in fmap['custom_statuses'].items()}

    def detail(section, options_section):
        out = []
        for key, d in fmap.get(section, {}).items():
            out.append({'key': key, 'id': d.get('id'), 'title': d.get('title'), 'attr': d.get('attr'),
                        'zendesk_type': d.get('zendesk_type'), 'type': d.get('type'),
                        'options': options_list(fmap.get(options_section, {}).get(key))})
        return out

    config = {
        '_source': 'provisioning/zendesk_field_map.json (gerado por script/servicedesk_zendesk_compat_config.py)',
        '_generated_from': fmap.get('_meta', {}).get('generated_at'),
        'ticket_fields': fields,
        'groups': groups,
        'via_channels': {k: v for k, v in system['via.channel']['map'].items()},
        'via_rel': system.get('via.source.rel', {}).get('map', {}),
        'priorities': system['priority']['map'],
        'types': system['type']['map'],
        'custom_statuses': statuses,
        'forms': {f.get('name'): int(zid) for zid, f in fmap.get('forms', {}).items()},
        'user_fields': detail('user_fields_detail', 'user_field_options'),
        'org_fields': detail('org_fields_detail', 'org_field_options'),
    }
    json.dump(config, sys.stdout, ensure_ascii=False, indent=1, sort_keys=False)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
