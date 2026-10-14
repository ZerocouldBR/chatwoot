"""Roteiros SINTÉTICOS de atendimento (pt-BR). Pessoas, agências, hotéis, CPF, cartão,
e-mail e telefone são FICTÍCIOS (CPF 123.456.789-09 e cartão 4111... são valores de teste).

Cada fala: (papel, texto). "A" = atendente, "C" = cliente.
O texto é escrito como se fala (números por extenso), para o TTS ler naturalmente.
`ref` é a transcrição de referência normalizada usada no cálculo de WER.
"""

DIALOGUES = {
    "bom_atendimento": [
        ("A", "B2B Reservas, bom dia! Meu nome é Carla, com quem eu falo?"),
        ("C", "Bom dia, Carla. Aqui é o Roberto, da agência Viagens Horizonte."),
        ("A", "Olá, Roberto, tudo bem? Como posso te ajudar hoje?"),
        ("C", "Eu fiz uma reserva para o hotel Mar Azul e o voucher não chegou para o cliente. "
              "Estou preocupado, porque o check-in é amanhã."),
        ("A", "Entendo a sua preocupação, Roberto, vamos resolver isso agora. Para confirmar a sua "
              "identidade, pode me informar o código da reserva e o CPF do titular da conta?"),
        ("C", "Claro. O código da reserva é quatro cinco nove dois. "
              "O CPF é um dois três, quatro cinco seis, sete oito nove, zero nove."),
        ("A", "Obrigada. Estou verificando aqui no sistema. Identifiquei que o voucher foi gerado, "
              "mas o e-mail do hóspede estava com um erro de digitação. Qual é o e-mail correto?"),
        ("C", "É roberto ponto silva arroba exemplo ponto com."),
        ("A", "Perfeito, já corrigi o e-mail e reenviei o voucher agora. Pode confirmar se chegou?"),
        ("C", "Chegou sim, muito obrigado!"),
        ("A", "Ótimo. O seu protocolo de atendimento é dois zero dois seis, um zero um três. "
              "Registrei tudo no ticket. Posso ajudar em mais alguma coisa?"),
        ("C", "Não, era só isso mesmo."),
        ("A", "Agradeço a ligação, Roberto. Desejo uma ótima estadia ao seu cliente. Tenha um bom dia!"),
    ],
    "atendimento_ruim": [
        ("A", "Alô."),
        ("C", "Alô, bom dia. Eu estou ligando porque a minha reserva foi cancelada e ninguém me "
              "explicou o motivo. Já é a terceira vez que eu ligo."),
        ("A", "Qual reserva?"),
        ("C", "A reserva do hotel Serra Verde, código sete sete um."),
        ("A", "Ah, isso aí não é comigo, é com o financeiro."),
        ("C", "Mas da última vez me disseram que era com o suporte. Isso é um absurdo, "
              "eu quero falar com um supervisor."),
        ("A", "O supervisor não está. O senhor pode ligar outra hora."),
        ("C", "E o meu cliente, como fica? Ele chega na sexta-feira."),
        ("A", "Não tem o que fazer agora. Vou ver se alguém te liga depois."),
        ("C", "Vocês não resolvem nada. Vou registrar uma reclamação."),
        ("A", "Tá bom. Tchau."),
    ],
    "cobranca_dados_sensiveis": [
        ("A", "B2B Reservas, boa tarde, aqui é o Marcos. Em que posso ajudar?"),
        ("C", "Boa tarde, Marcos. Quero atualizar o cartão de crédito da minha agência."),
        ("A", "Claro. Por segurança, não precisa me falar o número do cartão por telefone. "
              "Vou te enviar um link seguro por e-mail."),
        ("C", "Ah, mas eu já tenho aqui. O número é quatro um um um, um um um um, um um um um, um um um um."),
        ("A", "Entendo, mas não vou registrar esse número. Pode me confirmar um telefone para contato?"),
        ("C", "O meu telefone é onze, nove oito sete seis cinco, quatro três dois um."),
        ("A", "Obrigado. Enviei o link seguro agora. Vou retornar amanhã até as dez horas "
              "para confirmar a atualização. Mais alguma coisa?"),
        ("C", "Não, obrigado."),
        ("A", "Eu que agradeço. Boa tarde!"),
    ],
}

# Referências escritas como a transcrição ideal (números em dígitos, como o Whisper costuma escrever).
REFERENCES = {
    "bom_atendimento": (
        "B2B Reservas, bom dia! Meu nome é Carla, com quem eu falo? "
        "Bom dia, Carla. Aqui é o Roberto, da agência Viagens Horizonte. "
        "Olá, Roberto, tudo bem? Como posso te ajudar hoje? "
        "Eu fiz uma reserva para o hotel Mar Azul e o voucher não chegou para o cliente. "
        "Estou preocupado, porque o check-in é amanhã. "
        "Entendo a sua preocupação, Roberto, vamos resolver isso agora. Para confirmar a sua identidade, "
        "pode me informar o código da reserva e o CPF do titular da conta? "
        "Claro. O código da reserva é 4592. O CPF é 123 456 789 09. "
        "Obrigada. Estou verificando aqui no sistema. Identifiquei que o voucher foi gerado, mas o e-mail "
        "do hóspede estava com um erro de digitação. Qual é o e-mail correto? "
        "É roberto.silva@exemplo.com. "
        "Perfeito, já corrigi o e-mail e reenviei o voucher agora. Pode confirmar se chegou? "
        "Chegou sim, muito obrigado! "
        "Ótimo. O seu protocolo de atendimento é 2026 1013. Registrei tudo no ticket. "
        "Posso ajudar em mais alguma coisa? Não, era só isso mesmo. "
        "Agradeço a ligação, Roberto. Desejo uma ótima estadia ao seu cliente. Tenha um bom dia!"
    ),
    "atendimento_ruim": (
        "Alô. Alô, bom dia. Eu estou ligando porque a minha reserva foi cancelada e ninguém me explicou o "
        "motivo. Já é a terceira vez que eu ligo. Qual reserva? A reserva do hotel Serra Verde, código 771. "
        "Ah, isso aí não é comigo, é com o financeiro. Mas da última vez me disseram que era com o suporte. "
        "Isso é um absurdo, eu quero falar com um supervisor. O supervisor não está. O senhor pode ligar "
        "outra hora. E o meu cliente, como fica? Ele chega na sexta-feira. Não tem o que fazer agora. "
        "Vou ver se alguém te liga depois. Vocês não resolvem nada. Vou registrar uma reclamação. "
        "Tá bom. Tchau."
    ),
    "cobranca_dados_sensiveis": (
        "B2B Reservas, boa tarde, aqui é o Marcos. Em que posso ajudar? Boa tarde, Marcos. Quero atualizar "
        "o cartão de crédito da minha agência. Claro. Por segurança, não precisa me falar o número do "
        "cartão por telefone. Vou te enviar um link seguro por e-mail. Ah, mas eu já tenho aqui. O número é "
        "4111 1111 1111 1111. Entendo, mas não vou registrar esse número. Pode me confirmar um telefone para "
        "contato? O meu telefone é 11 98765 4321. Obrigado. Enviei o link seguro agora. Vou retornar amanhã "
        "até as 10 horas para confirmar a atualização. Mais alguma coisa? Não, obrigado. Eu que agradeço. "
        "Boa tarde!"
    ),
}
