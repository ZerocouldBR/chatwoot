#!/usr/bin/env python3
"""Valida os JSON de workflow n8n do ServiceDesk (estrutura de nós e conexões + regras do projeto).

Uso: python3 tools/validate_workflows.py [--node-check] [--openapi caminho/openapi.json]

Verifica, por arquivo:
  1. chaves de importação (name, nodes, connections, settings) e JSON válido;
  2. nós: id único (UUID), nome único, tipo e typeVersion dentro do conjunto usado na instância do cliente,
     position [x, y], parâmetros obrigatórios por tipo;
  3. conexões: origem e destino existem, tipo 'main', índice de saída válido (IF = 2, Switch = nº de regras);
     todo nó não-gatilho tem entrada; todo gatilho tem saída;
  4. expressões: '={{' balanceado, $('Nó') referencia nó existente;
  5. segurança: credenciais só por placeholder REPLACE_*, nenhum valor que pareça segredo, webhook do sd-ops
     com headerAuth, path de webhook único entre arquivos;
  6. contrato: chamadas ao sd-ops com X-SD-Origin, X-SD-Workflow e Idempotency-Key; escritas no Chatwoot com
     sd_origin (mensagens); POST custom_attributes com merge=true;
  7. --node-check: compila o JavaScript de cada nó Code com `node --check` (se o Node.js existir);
  8. --openapi: confere os caminhos do sd-ops usados com o OpenAPI do A2 (relatório, não falha).
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
WF_DIR = os.path.normpath(os.path.join(HERE, "..", "workflows"))

# tipos/versões já usados na instância do cliente (exportação de 219 workflows, 2026-10-13)
ALLOWED = {
    "n8n-nodes-base.webhook": {2, 2.1},
    "n8n-nodes-base.code": {2},
    "n8n-nodes-base.if": {2, 2.2, 2.3},
    "n8n-nodes-base.switch": {3, 3.2, 3.4},
    "n8n-nodes-base.set": {3.4},
    "n8n-nodes-base.httpRequest": {4.2, 4.3, 4.4},
    "n8n-nodes-base.scheduleTrigger": {1.1, 1.2, 1.3},
    "n8n-nodes-base.wait": {1.1},
    "n8n-nodes-base.noOp": {1},
    "n8n-nodes-base.errorTrigger": {1},
    "n8n-nodes-base.respondToWebhook": {1.1, 1.4, 1.5},
}
TRIGGERS = {"n8n-nodes-base.webhook", "n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.errorTrigger"}
SECRET_RE = re.compile(r"(sdsvc_[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]{16,}|eyJ[A-Za-z0-9_-]{10,}\.|"
                       r"[A-Fa-f0-9]{40,}|api[_-]?key\s*[:=]\s*['\"][^'\"]{8,})")
REF_RE = re.compile(r"\$\('([^']+)'\)")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, f, msg):
        self.errors.append("%s: %s" % (f, msg))

    def warn(self, f, msg):
        self.warnings.append("%s: %s" % (f, msg))


def walk_strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_strings(v)
    elif isinstance(o, str):
        yield o


def n_outputs(node):
    t = node["type"]
    if t == "n8n-nodes-base.if":
        return 2
    if t == "n8n-nodes-base.switch":
        return len(node["parameters"].get("rules", {}).get("values", []))
    return 1


def validate_file(path, rep, paths_seen, sdops_used):
    f = os.path.basename(path)
    try:
        wf = json.load(open(path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        rep.err(f, "JSON inválido: %s" % e)
        return []
    for k in ("name", "nodes", "connections", "settings"):
        if k not in wf:
            rep.err(f, "falta a chave '%s'" % k)
    nodes = wf.get("nodes", [])
    by_name = {}
    ids = set()
    codes = []
    for n in nodes:
        name = n.get("name")
        if not name:
            rep.err(f, "nó sem nome")
            continue
        if name in by_name:
            rep.err(f, "nome de nó repetido: %s" % name)
        by_name[name] = n
        try:
            uuid.UUID(n.get("id", ""))
        except ValueError:
            rep.err(f, "id inválido em %s" % name)
        if n.get("id") in ids:
            rep.err(f, "id repetido em %s" % name)
        ids.add(n.get("id"))
        t, v = n.get("type"), n.get("typeVersion")
        if t not in ALLOWED:
            rep.err(f, "tipo não permitido em %s: %s" % (name, t))
        elif v not in ALLOWED[t]:
            rep.err(f, "typeVersion %s não usada na instância para %s (%s)" % (v, t, name))
        pos = n.get("position")
        if not (isinstance(pos, list) and len(pos) == 2 and all(isinstance(x, (int, float)) for x in pos)):
            rep.err(f, "position inválida em %s" % name)
        p = n.get("parameters", {})
        if t == "n8n-nodes-base.webhook":
            if not p.get("path"):
                rep.err(f, "webhook sem path (%s)" % name)
            if p.get("path") in paths_seen:
                rep.err(f, "path de webhook repetido: %s (também em %s)" % (p.get("path"), paths_seen[p.get("path")]))
            paths_seen[p.get("path")] = f
            if not n.get("webhookId"):
                rep.err(f, "webhook sem webhookId (%s)" % name)
            if p.get("path", "").startswith("sd/wf") and "chatwoot" not in p.get("path", ""):
                if p.get("authentication") != "headerAuth" or "httpHeaderAuth" not in (n.get("credentials") or {}):
                    rep.err(f, "webhook do sd-ops sem headerAuth (%s)" % name)
        if t == "n8n-nodes-base.code":
            if not p.get("jsCode"):
                rep.err(f, "Code sem jsCode (%s)" % name)
            codes.append((name, p.get("jsCode", "")))
        if t == "n8n-nodes-base.httpRequest":
            url = p.get("url", "")
            if not url:
                rep.err(f, "HTTP sem url (%s)" % name)
            hdrs = {h["name"]: h["value"] for h in p.get("headerParameters", {}).get("parameters", [])}
            method = p.get("method", "GET")
            if "sdops_base_url" in url:
                for h in ("X-SD-Origin", "X-SD-Workflow", "Idempotency-Key"):
                    if h not in hdrs:
                        rep.err(f, "chamada ao sd-ops sem header %s (%s)" % (h, name))
                path_ = re.sub(r"\{\{[^}]*\}\}", "{x}", url.split("sdops_base_url }}", 1)[-1])
                sdops_used.add("%s %s" % (method, path_))
            if "chatwoot_base_url" in url and method == "POST":
                body = p.get("jsonBody", "")
                if url.endswith("/messages") and "sd_origin" not in body:
                    rep.err(f, "mensagem no Chatwoot sem sd_origin (%s)" % name)
                if "custom_attributes" in url and "merge" not in body:
                    rep.err(f, "custom_attributes sem merge=true (%s)" % name)
            if p.get("authentication") != "genericCredentialType" or "httpHeaderAuth" not in (n.get("credentials") or {}):
                rep.err(f, "HTTP sem credencial Header Auth (%s)" % name)
        for cname, cref in (n.get("credentials") or {}).items():
            if not str(cref.get("id", "")).startswith("REPLACE_"):
                rep.err(f, "credencial %s de %s não é placeholder REPLACE_*" % (cname, name))
        for s in walk_strings(p):
            if SECRET_RE.search(s):
                rep.err(f, "valor parecido com segredo em %s: %s..." % (name, SECRET_RE.search(s).group(0)[:12]))
            if s.startswith("=") and s.count("{{") != s.count("}}"):
                rep.err(f, "expressão desbalanceada em %s" % name)
            for ref in REF_RE.findall(s):
                if ref not in [x.get("name") for x in nodes]:
                    rep.err(f, "referência a nó inexistente $('%s') em %s" % (ref, name))
    # conexões
    conns = wf.get("connections", {})
    has_input = set()
    for src, kinds in conns.items():
        if src not in by_name:
            rep.err(f, "conexão de nó inexistente: %s" % src)
            continue
        for kind, outs in kinds.items():
            if kind != "main":
                rep.err(f, "conexão de tipo %s em %s" % (kind, src))
            if len(outs) > n_outputs(by_name[src]):
                rep.err(f, "%s tem %d saídas conectadas, máximo %d" % (src, len(outs), n_outputs(by_name[src])))
            for lst in outs:
                for c in lst:
                    if c.get("node") not in by_name:
                        rep.err(f, "conexão para nó inexistente: %s -> %s" % (src, c.get("node")))
                    if c.get("type") != "main" or c.get("index") != 0:
                        rep.err(f, "conexão inválida %s -> %s" % (src, c.get("node")))
                    has_input.add(c.get("node"))
    trig = [n for n in nodes if n["type"] in TRIGGERS]
    if not trig:
        rep.err(f, "workflow sem gatilho")
    for n in nodes:
        if n["type"] in TRIGGERS:
            if n["name"] not in conns:
                rep.err(f, "gatilho sem saída: %s" % n["name"])
        elif n["name"] not in has_input:
            rep.err(f, "nó sem entrada (solto): %s" % n["name"])
    if wf.get("active"):
        rep.err(f, "workflow exportado como ativo (deve ser importado inativo)")
    return codes


def node_check(all_codes, rep):
    node = shutil.which("node")
    if not node:
        rep.warn("node-check", "Node.js não encontrado; JavaScript não compilado")
        return 0
    n = 0
    with tempfile.TemporaryDirectory() as d:
        for f, name, js in all_codes:
            p = os.path.join(d, "c%d.js" % n)
            # o nó Code roda o corpo dentro de uma função assíncrona
            open(p, "w", encoding="utf-8").write("async function __n8n(){\n%s\n}\n" % js)
            r = subprocess.run([node, "--check", p], capture_output=True, text=True)
            if r.returncode != 0:
                linhas = [x for x in (r.stderr or "").splitlines() if "Error" in x] or (r.stderr or "?").splitlines()[-1:]
                rep.err(f, "JavaScript inválido em %s: %s" % (name, linhas[0].strip()))
            n += 1
    return n


def main():
    rep = Report()
    paths_seen = {}
    sdops_used = set()
    all_codes = []
    files = sorted(glob.glob(os.path.join(WF_DIR, "*.json")))
    if not files:
        print("nenhum workflow em %s" % WF_DIR)
        return 1
    for p in files:
        for name, js in validate_file(p, rep, paths_seen, sdops_used):
            all_codes.append((os.path.basename(p), name, js))
    compiled = node_check(all_codes, rep) if "--node-check" in sys.argv else 0
    if "--openapi" in sys.argv:
        spec = json.load(open(sys.argv[sys.argv.index("--openapi") + 1], encoding="utf-8"))
        have = set()
        for path_, ops in spec.get("paths", {}).items():
            norm = re.sub(r"\{[^}]+\}", "{x}", path_.replace("/sd-ops/api/v1", ""))
            for m in ops:
                have.add("%s %s" % (m.upper(), norm))
        print("Conferência com o OpenAPI (%s):" % sys.argv[sys.argv.index("--openapi") + 1])
        for u in sorted(sdops_used):
            m, p_ = u.split(" ", 1)
            print("  %-8s %s %s" % ("existe" if "%s %s" % (m, p_) in have else "PENDENTE", m, p_))
    print("arquivos: %d | nós Code compilados: %d | erros: %d | avisos: %d" %
          (len(files), compiled, len(rep.errors), len(rep.warnings)))
    for w in rep.warnings:
        print("AVISO", w)
    for e in rep.errors:
        print("ERRO", e)
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
