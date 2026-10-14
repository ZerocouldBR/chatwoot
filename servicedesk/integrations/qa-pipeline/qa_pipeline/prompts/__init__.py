"""Prompts versionados. O conteúdo de cada arquivo é registrado em qa.prompt_versions com sha256;
a avaliação guarda o id da versão usada. Mudou o texto? Crie um arquivo novo (_v2), não edite o antigo."""
from __future__ import annotations

import hashlib
import os
from typing import Dict, Tuple

HERE = os.path.dirname(__file__)
CURRENT = {"qa": "v1", "summary": "v1"}


def load(kind: str, version: str = None) -> Tuple[str, str, str]:
    version = version or CURRENT[kind]
    with open(os.path.join(HERE, f"{kind}_{version}.txt"), encoding="utf-8") as fh:
        template = fh.read()
    return version, template, hashlib.sha256(template.encode("utf-8")).hexdigest()


def split(template: str) -> Dict[str, str]:
    system, _, user = template.partition("### USER")
    return {"system": system.replace("### SYSTEM", "").strip(), "user": user.strip()}


def render(template: str, **values) -> Dict[str, str]:
    parts = split(template)
    user = parts["user"]
    for k, v in values.items():
        user = user.replace("{" + k + "}", str(v))
    return {"system": parts["system"], "user": user}
