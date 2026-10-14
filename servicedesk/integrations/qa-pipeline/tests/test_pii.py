from qa_pipeline.pii import mask_segments, mask_text, spoken_to_digits


def test_cpf_formats():
    assert mask_text("O CPF é 123.456.789-09.") == "O CPF é [CPF]."
    assert mask_text("O CPF é 123 456 789 09.") == "O CPF é [CPF]."
    assert mask_text("cpf 12345678909") == "cpf [CPF]"


def test_spoken_digits_become_masked():
    assert spoken_to_digits("um dois três, quatro cinco seis") == "123 456"
    assert mask_text("O CPF é um dois três, quatro cinco seis, sete oito nove, zero nove.") == "O CPF é [CPF]."


def test_card_luhn_and_cvv():
    assert mask_text("O número é 4111 1111 1111 1111.") == "O número é [CARTAO]."
    assert mask_text("cartão 4111-1111-1111-1111 cvv 123") == "cartão [CARTAO] cvv [CVV]"


def test_email_written_and_spoken():
    assert mask_text("É roberto.silva@exemplo.com.") == "É [EMAIL]."
    assert mask_text("é roberto ponto silva arroba exemplo ponto com") == "é [EMAIL]"


def test_phone_and_password():
    assert mask_text("O meu telefone é 11 98765 4321.") == "O meu telefone é [TELEFONE]."
    assert mask_text("whatsapp +55 11 98765-4321") == "whatsapp [TELEFONE]"
    assert mask_text("a minha senha é Hotel@2026") == "a minha senha é [SENHA]"


def test_business_numbers_preserved():
    # protocolo e código de reserva não são dados pessoais
    assert mask_text("O seu protocolo de atendimento é 2026 1013.") == "O seu protocolo de atendimento é 2026 1013."
    assert mask_text("O código da reserva é 4592.") == "O código da reserva é 4592."
    assert mask_text("check-in dia 15 às 14h") == "check-in dia 15 às 14h"


def test_number_split_across_segments():
    out, counts = mask_segments(["o CPF é 123 456", "789 09 confere?"])
    joined = " ".join(out)
    assert "123" not in joined and "789" not in joined
    assert sum(counts.values()) >= 1


def test_real_whisper_outputs_from_benchmark():
    """Saídas REAIS do faster-whisper small sobre os áudios sintéticos (dev/bench_stt.py)."""
    a = mask_text("O CPF é um dois três, quatro cinco seis, sete oito nove, zero nove.")
    b = mask_text("É Roberto.silvarrobexemplo.com.")
    c = mask_text("O número é 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1. Entendo")
    d = mask_text("O meu telefone é 11, 987654321. Obrigado.")
    e = mask_text("Patoom, seu protocolo de atendimento é 2026-1013.")
    assert a == "O CPF é [CPF]."
    assert b == "É [EMAIL]."
    assert "4, 1, 1" not in c and "[" in c
    assert d == "O meu telefone é [TELEFONE]. Obrigado."
    assert "2026-1013" in e
