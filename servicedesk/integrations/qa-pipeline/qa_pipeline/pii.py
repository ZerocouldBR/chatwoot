"""Mascaramento de dados pessoais ANTES de qualquer LLM, log ou tela.

Cobre: CPF, CNPJ, cartão (Luhn), CVV, e-mail (escrito ou ditado: "fulano arroba exemplo ponto
com"), telefone BR, senha ditada e longas sequências numéricas. Números ditados por extenso
("um dois três ...") são convertidos para dígitos antes da detecção, porque o STT pode escrever
de um jeito ou de outro.

Limite conhecido: um número dividido entre dois segmentos do STT é tratado por segmento e pelo
par de segmentos vizinhos (ver mask_segments), não pela conversa inteira.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Dict, List, Tuple

DIGIT_WORDS = {
    "zero": "0", "um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "três": "3",
    "quatro": "4", "cinco": "5", "seis": "6", "meia": "6", "sete": "7", "oito": "8", "nove": "9",
}
_WORD_RE = re.compile(r"\b(" + "|".join(sorted(DIGIT_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
# Sequência de >=4 palavras-dígito seguidas (com vírgula/espaço/"e") vira dígitos.
_SPOKEN_RUN = re.compile(
    r"\b(?:(?:" + "|".join(sorted(DIGIT_WORDS, key=len, reverse=True)) + r")[\s,.;-]+){3,}(?:"
    + "|".join(sorted(DIGIT_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
SPOKEN_EMAIL = re.compile(
    r"\b[\w]+(?:\s+(?:ponto|underline|traço|tracinho|hífen)\s+[\w]+)*\s+arroba\s+[\w]+(?:\s+ponto\s+[\w]+)+",
    re.IGNORECASE)
CNPJ = re.compile(r"\b\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}\b")
CPF = re.compile(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s.]?\d{2}\b")
# Sequências de dígitos com separadores (espaço, vírgula, ponto, hífen, barra).
DIGIT_RUN = re.compile(r"(?<![\w@])\+?\d(?:\d|[\s.,/-]{1,2}(?=\d)){6,}\d(?![\w@])")
# E-mail que o STT escreveu sem "@" (ex.: "Roberto.silvarrobexemplo.com"): domínio com ponto antes.
EMAIL_GARBLED = re.compile(r"\b[\w-]+(?:\.[\w-]+)+\.(?:com|net|org|br)(?:\.br)?\b", re.IGNORECASE)
CVV = re.compile(r"\b(cvv|cvc|c[oó]digo de seguran[cç]a)\b[\s:é,]*(\d{3,4})", re.IGNORECASE)
PASSWORD = re.compile(r"\b(senha)\b(\s+(?:é|e|eh|:)?\s*)(\S+)", re.IGNORECASE)

TAGS = {"cpf": "[CPF]", "cnpj": "[CNPJ]", "cartao": "[CARTAO]", "cvv": "[CVV]", "email": "[EMAIL]",
        "telefone": "[TELEFONE]", "senha": "[SENHA]", "numero": "[NUMERO]"}


def _luhn(d: str) -> bool:
    total, alt = 0, False
    for ch in reversed(d):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def _cpf_valid(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    for i in (9, 10):
        s = sum(int(d[j]) * ((i + 1) - j) for j in range(i))
        if ((s * 10) % 11) % 10 != int(d[i]):
            return False
    return True


def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def spoken_to_digits(text: str) -> str:
    """'um dois três, quatro cinco seis' -> '123 456'. Só converte sequências de 4+ dígitos falados."""
    def conv(m):
        out, prev_sep = [], ""
        for tok in re.split(r"([\s,.;-]+)", m.group(0)):
            key = _strip_accents(tok.lower())
            if key in DIGIT_WORDS or tok.lower() in DIGIT_WORDS:
                out.append(DIGIT_WORDS.get(tok.lower(), DIGIT_WORDS.get(key)))
            elif tok:
                out.append(" " if "," in tok or ";" in tok else "")
        return "".join(out).strip()
    return _SPOKEN_RUN.sub(conv, text)


def _classify_run(raw: str, context: str) -> str:
    digits = re.sub(r"\D", "", raw)
    n = len(digits)
    ctx = _strip_accents(context.lower())
    if n == 11 and (_cpf_valid(digits) or "cpf" in ctx):
        return "cpf"
    if n == 14 and "cnpj" in ctx:
        return "cnpj"
    if 13 <= n <= 19 and (_luhn(digits) or "cartao" in ctx or "credito" in ctx):
        return "cartao"
    if n in (10, 11, 12, 13) and ("telefone" in ctx or "celular" in ctx or "whats" in ctx or raw.startswith("+")
                                  or (n == 11 and digits[2] == "9")):
        return "telefone"
    if n == 14:
        return "cnpj"
    if n == 11 and _cpf_valid(digits):
        return "cpf"
    # Protocolo/código de reserva não é dado pessoal: mantém (o atendente precisa dele no resumo).
    if re.search(r"(protocolo|reserva|pedido|chamado|ticket)\W*(de atendimento\W*)?(e|é|eh|:|numero|n[uú]mero)?\W*$", ctx[-45:]):
        return ""
    if n >= 8:
        return "numero"
    return ""


def mask_text(text: str, counts: Counter = None) -> str:
    counts = counts if counts is not None else Counter()
    t = spoken_to_digits(text)

    def sub(regex, kind, s, group=None):
        def rep(m):
            counts[kind] += 1
            if group is None:
                return TAGS[kind]
            return m.group(0).replace(m.group(group), TAGS[kind])
        return regex.sub(rep, s)

    t = sub(EMAIL, "email", t)
    t = sub(SPOKEN_EMAIL, "email", t)
    t = sub(EMAIL_GARBLED, "email", t)
    t = sub(CVV, "cvv", t, group=2)
    t = PASSWORD.sub(lambda m: (counts.update(["senha"]) or "") + m.group(1) + m.group(2) + TAGS["senha"], t)
    t = sub(CNPJ, "cnpj", t)

    def run_rep(m):
        start = max(0, m.start() - 60)
        kind = _classify_run(m.group(0), t[start:m.start()])
        if not kind:
            return m.group(0)
        counts[kind] += 1
        return TAGS[kind]

    t = DIGIT_RUN.sub(run_rep, t)
    t = sub(CPF, "cpf", t)
    return t


def mask_segments(texts: List[str]) -> Tuple[List[str], Dict[str, int]]:
    """Mascara cada segmento e também números que atravessam a fronteira entre dois segmentos."""
    counts: Counter = Counter()
    masked = [mask_text(x, counts) for x in texts]
    for i in range(len(masked) - 1):
        a, b = masked[i], masked[i + 1]
        tail = re.search(r"(\d[\d\s.,-]*)$", a)
        head = re.match(r"^\s*([\d][\d\s.,-]*)", b)
        if tail and head:
            joined = mask_text(tail.group(1) + " " + head.group(1), Counter())
            if "[" in joined:
                kind = next((k for k, v in TAGS.items() if v in joined), "numero")
                counts[kind] += 1
                masked[i] = a[: tail.start()] + TAGS[kind]
                masked[i + 1] = b[head.end():].lstrip() or TAGS[kind]
    return masked, dict(counts)


def contains_pii(text: str) -> bool:
    c: Counter = Counter()
    mask_text(text, c)
    return sum(c.values()) > 0
