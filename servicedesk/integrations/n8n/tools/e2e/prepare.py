#!/usr/bin/env python3
"""Prepara a cópia de TESTE dos workflows para o e2e (nunca usar na instância do cliente):
URLs apontando para o mock, dry_run desligado, horário liberado, supervisor fictício e credenciais falsas.
Uso: python3 prepare.py <dir_workflows> <dir_saida>
"""
import glob
import json
import os
import sys

src, out = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(out, "workflows"), exist_ok=True)
OVR = {
    "sdops_base_url": "http://sd-mock:8080/sd-ops/api/v1",
    "chatwoot_base_url": "http://sd-mock:8080",
    "dry_run": False,
    "hora_inicio": 0,
    "hora_fim": 24,
    "whatsapp_inbox_id": 41,
    "email_inbox_id": 42,
    "template_nome": "pos_atendimento_teste",
    "supervisores_por_time": '{"*": [3]}',
}
for f in sorted(glob.glob(os.path.join(src, "*.json"))):
    wf = json.load(open(f, encoding="utf-8"))
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.set":
            for a in n["parameters"]["assignments"]["assignments"]:
                if a["name"] in OVR:
                    a["value"] = OVR[a["name"]]
        if n["type"] == "n8n-nodes-base.webhook" and "REPLACE_SEGREDO_LONGO" in n["parameters"].get("path", ""):
            pass  # o cenário usa o mesmo placeholder como segredo de teste
    json.dump(wf, open(os.path.join(out, "workflows", os.path.basename(f)), "w", encoding="utf-8"), ensure_ascii=False)

creds = [
    {"id": "REPLACE_CRED_SDOPS_SERVICE_TOKEN", "name": "SD-OPS: token de serviço do n8n (Authorization: Bearer)",
     "type": "httpHeaderAuth", "data": {"name": "Authorization", "value": "Bearer teste-e2e-falso"}},
    {"id": "REPLACE_CRED_CHATWOOT_N8N", "name": "ServiceDesk/Chatwoot: api_access_token da Integração n8n",
     "type": "httpHeaderAuth", "data": {"name": "api_access_token", "value": "teste-e2e-falso"}},
    {"id": "REPLACE_CRED_SDOPS_WEBHOOK_TOKEN", "name": "SD-OPS -> n8n: X-SD-Webhook-Token",
     "type": "httpHeaderAuth", "data": {"name": "X-SD-Webhook-Token", "value": "token-de-teste-e2e"}},
]
json.dump(creds, open(os.path.join(out, "creds.json"), "w", encoding="utf-8"))
print("ok:", len(glob.glob(os.path.join(out, "workflows", "*.json"))), "workflows de teste")
