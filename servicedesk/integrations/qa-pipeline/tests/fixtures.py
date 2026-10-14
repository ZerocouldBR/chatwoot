"""Transcrições SINTÉTICAS no formato que o Whisper produz (números em dígitos). Dados fictícios."""

GOOD = [
    (0.0, 4.2, "B2B Reservas, bom dia! Meu nome é Carla, com quem eu falo?"),
    (4.8, 8.6, "Bom dia, Carla. Aqui é o Roberto, da agência Viagens Horizonte."),
    (9.2, 12.0, "Olá, Roberto, tudo bem? Como posso te ajudar hoje?"),
    (12.6, 20.1, "Eu fiz uma reserva para o hotel Mar Azul e o voucher não chegou para o cliente."),
    (20.1, 23.0, "Estou preocupado, porque o check-in é amanhã."),
    (23.6, 31.9, "Entendo a sua preocupação, Roberto, vamos resolver isso agora. Para confirmar a sua identidade, "
                 "pode me informar o código da reserva e o CPF do titular da conta?"),
    (32.5, 40.2, "Claro. O código da reserva é 4592. O CPF é 123 456 789 09."),
    (40.8, 50.3, "Obrigada. Estou verificando aqui no sistema. Identifiquei que o voucher foi gerado, mas o e-mail "
                 "do hóspede estava com um erro de digitação. Qual é o e-mail correto?"),
    (50.9, 54.0, "É roberto.silva@exemplo.com."),
    (54.6, 59.8, "Perfeito, já corrigi o e-mail e reenviei o voucher agora. Pode confirmar se chegou?"),
    (60.4, 62.3, "Chegou sim, muito obrigado!"),
    (62.9, 70.5, "Ótimo. O seu protocolo de atendimento é 2026 1013. Registrei tudo no ticket. "
                 "Posso ajudar em mais alguma coisa?"),
    (71.1, 72.9, "Não, era só isso mesmo."),
    (73.5, 80.6, "Agradeço a ligação, Roberto. Desejo uma ótima estadia ao seu cliente. Tenha um bom dia!"),
]

BAD = [
    (0.0, 0.9, "Alô."),
    (1.5, 9.8, "Alô, bom dia. Eu estou ligando porque a minha reserva foi cancelada e ninguém me explicou o motivo. "
               "Já é a terceira vez que eu ligo."),
    (10.4, 11.3, "Qual reserva?"),
    (11.9, 15.6, "A reserva do hotel Serra Verde, código 771."),
    (16.2, 19.0, "Ah, isso aí não é comigo, é com o financeiro."),
    (19.6, 26.9, "Mas da última vez me disseram que era com o suporte. Isso é um absurdo, eu quero falar com um "
                 "supervisor."),
    (27.5, 30.8, "O supervisor não está. O senhor pode ligar outra hora."),
    (31.4, 34.6, "E o meu cliente, como fica? Ele chega na sexta-feira."),
    (35.2, 39.4, "Não tem o que fazer agora. Vou ver se alguém te liga depois."),
    (40.0, 44.1, "Vocês não resolvem nada. Vou registrar uma reclamação."),
    (44.7, 46.0, "Tá bom. Tchau."),
]


def as_json(rows, duration=None, partial=False, channel=None):
    return {"language": "pt", "duration_s": duration or (rows[-1][1] + 0.5 if rows else 8.0), "partial": partial,
            "segments": [{"start": a, "end": b, "text": t, "avg_logprob": -0.25, "no_speech_prob": 0.02,
                          **({"channel": channel} if channel is not None else {})} for a, b, t in rows]}
