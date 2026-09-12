"""Taxa-base de preço: em quantas janelas históricas este movimento aconteceu?

É a parte do projeto em que a taxa-base é **realmente comparável** com o preço do
mercado, e vale explicar por que ela é melhor que as famílias de calendário.

"O Fed sobe juros em 2026?" tem taxa-base de frequência anual, e um ano civil é
uma unidade arbitrária: não tem nada a ver com a pergunta além de aparecer no
texto dela. Já "o bitcoin toca US$ 150 mil até 31 de dezembro?" tem uma
estrutura que a história responde direto:

- o bitcoin está em **S₀** hoje;
- faltam **h** dias até a data;
- a pergunta é se ele sobe **alvo/S₀** em algum momento dentro desses h dias.

Então varro a série inteira do ativo, pego toda janela de h dias, e conto em
quantas delas o preço subiu essa mesma razão em algum momento. Isso é uma
reamostragem empírica: não supõe distribuição nenhuma, o que importa muito aqui
porque bitcoin e petróleo têm cauda gorda e qualquer conta que suponha normal
subestima o extremo, que é exatamente o que estes mercados perguntam.

**É TOQUE e não fechamento.** "Dip to", "hit", "reach" perguntam se o preço
ENCOSTA no nível em algum momento da janela, não se termina lá. A diferença é
grande: bater US$ 150 mil e voltar resolve o mercado em SIM. Por isso a conta usa
o máximo (ou o mínimo) corrente da janela, nunca a ponta.

**As duas ressalvas que ficam, e nenhuma some com mais dado:**

1. **Janelas deslizantes se sobrepõem.** Duas janelas de 90 dias que começam com
   um dia de diferença compartilham 89. O n que sai daqui é o número de janelas,
   e o n EFETIVO é muito menor — perto de N/h, o de janelas que não se tocam.
   Os dois vão para a tela.
2. **A história do ativo não é estacionária.** A volatilidade do bitcoin em 2015
   não é a de 2026, e o petróleo de 1986 não é o de agora. A taxa-base mistura
   regimes, e não há conserto honesto: recortar só o período recente troca esse
   viés por um n minúsculo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Abaixo disto a fração medida é ruído: com 20 janelas efetivas, uma única
# mudando de lado move a taxa-base em cinco pontos percentuais.
JANELAS_EFETIVAS_MINIMAS = 20


@dataclass
class TaxaDeToque:
    valor: float
    janelas: int
    janelas_efetivas: int
    razao_exigida: float
    preco_de_hoje: float
    alvo: float
    horizonte_dias: int
    primeiro_dia: date
    ultimo_dia: date
    direcao: str  # "acima" ou "abaixo"


class SemAmostra(RuntimeError):
    """A série não cobre um horizonte deste tamanho, ou cobre poucas vezes."""


def _passos_e_janelas(
    serie: list[tuple[date, float]], horizonte_dias: int
) -> tuple[int, int, int]:
    """Converte o horizonte em passos da série e diz quantas janelas cabem.

    O horizonte da pergunta é em dias de CALENDÁRIO e a série tem só os dias em
    que houve preço. Converter pela razão medida na própria série é melhor que
    fixar 252/365: o ouro da LBMA tem leilão em dia útil, o bitcoin negocia todo
    dia, e o mesmo número fixo estaria errado num dos dois.

    Devolve `(passos, janelas, janelas efetivas)`. As efetivas são as que NÃO se
    sobrepõem — perto de N/h — e são elas que valem como tamanho de amostra.
    """
    dias_de_calendario = (serie[-1][0] - serie[0][0]).days
    if dias_de_calendario <= 0:
        raise SemAmostra("série sem extensão de tempo")

    passos_por_dia = len(serie) / dias_de_calendario
    passos = max(1, round(horizonte_dias * passos_por_dia))
    if passos >= len(serie):
        raise SemAmostra(
            f"o horizonte de {horizonte_dias} dias não cabe na série "
            f"({serie[0][0]} a {serie[-1][0]})"
        )

    janelas = len(serie) - passos
    efetivas = janelas // passos
    if efetivas < JANELAS_EFETIVAS_MINIMAS:
        raise SemAmostra(
            f"só {efetivas} janelas independentes de {horizonte_dias} dias cabem na série "
            f"(mínimo {JANELAS_EFETIVAS_MINIMAS}) — a série é curta demais para este horizonte"
        )
    return passos, janelas, efetivas


def taxa_de_toque(
    serie: list[tuple[date, float]],
    alvo: float,
    horizonte_dias: int,
    direcao: str = "acima",
) -> TaxaDeToque:
    """Fração das janelas de `horizonte_dias` em que o ativo tocou `alvo`.

    `serie` é `(dia, preço)` ordenado. `alvo` está na unidade do preço. A conta é
    feita em RAZÃO e não em diferença — o bitcoin a US$ 77 mil subindo para
    US$ 150 mil é 1,94x, e é essa razão que se procura na história, não os
    US$ 73 mil de diferença, que em 2015 seriam um movimento de 7.000%.
    """
    if direcao not in ("acima", "abaixo"):
        raise ValueError(f"direção desconhecida: {direcao!r}")

    limpa = [(d, p) for d, p in serie if p == p and p > 0]
    if len(limpa) < 2:
        raise SemAmostra("série sem preço utilizável")

    hoje = limpa[-1][1]
    if not (alvo == alvo and alvo > 0):
        raise SemAmostra(f"alvo inválido: {alvo!r}")

    razao = alvo / hoje

    # Um alvo que já foi atingido não é pergunta sobre o futuro: a resposta é
    # 100% e o mercado provavelmente já resolveu. Devolver 1,0 aqui poria um
    # "100%" na tela ao lado de um preço de 0,02 e pareceria a maior
    # discrepância do painel, quando é só a pergunta estar vencida.
    if (direcao == "acima" and razao <= 1.0) or (direcao == "abaixo" and razao >= 1.0):
        raise SemAmostra(
            f"o alvo ({alvo:g}) já está do lado certo do preço de hoje ({hoje:g}) — "
            "a pergunta não é sobre um movimento futuro"
        )

    passos, janelas, efetivas = _passos_e_janelas(limpa, horizonte_dias)

    precos = [p for _, p in limpa]
    tocaram = 0
    for inicio in range(janelas):
        partida = precos[inicio]
        trecho = precos[inicio + 1 : inicio + 1 + passos]
        if not trecho:
            continue
        extremo = max(trecho) if direcao == "acima" else min(trecho)
        if (direcao == "acima" and extremo / partida >= razao) or (
            direcao == "abaixo" and extremo / partida <= razao
        ):
            tocaram += 1

    return TaxaDeToque(
        valor=tocaram / janelas,
        janelas=janelas,
        janelas_efetivas=efetivas,
        razao_exigida=razao,
        preco_de_hoje=hoje,
        alvo=alvo,
        horizonte_dias=horizonte_dias,
        primeiro_dia=limpa[0][0],
        ultimo_dia=limpa[-1][0],
        direcao=direcao,
    )


def taxa_de_fechamento(
    serie: list[tuple[date, float]],
    alvo: float,
    horizonte_dias: int,
    direcao: str = "acima",
) -> TaxaDeToque:
    """Fração das janelas em que o ativo TERMINOU do lado pedido. Não é toque.

    "O bitcoin estará acima de US$ 78.000 **no dia** 12 de setembro?" e "o
    bitcoin **toca** US$ 78.000 até 12 de setembro?" são perguntas diferentes, e
    a segunda é sempre mais provável — encostar e voltar resolve uma em SIM e a
    outra em NÃO.

    Confundir as duas não dá erro nenhum, dá um número plausível e errado.
    Aconteceu: a família de toque pegava "be above $78,000 on September 12" pelo
    "above" e respondia **34,1%** para uma pergunta que o mercado precificava a
    5,5%. A diferença apareceria na tela como a maior discrepância do painel,
    quando era eu respondendo outra coisa.

    Não tem o guard de "o alvo já está do lado certo" que a `taxa_de_toque` tem:
    aqui isso é uma pergunta legítima — o ativo está acima do alvo e se pergunta
    se ele CONTINUA acima na data.
    """
    if direcao not in ("acima", "abaixo"):
        raise ValueError(f"direção desconhecida: {direcao!r}")

    limpa = [(d, p) for d, p in serie if p == p and p > 0]
    if len(limpa) < 2:
        raise SemAmostra("série sem preço utilizável")
    if not (alvo == alvo and alvo > 0):
        raise SemAmostra(f"alvo inválido: {alvo!r}")

    hoje = limpa[-1][1]
    razao = alvo / hoje
    passos, janelas, efetivas = _passos_e_janelas(limpa, horizonte_dias)

    precos_ = [p for _, p in limpa]
    acertaram = 0
    for inicio in range(janelas):
        partida = precos_[inicio]
        fim = precos_[inicio + passos]
        if (direcao == "acima" and fim / partida >= razao) or (
            direcao == "abaixo" and fim / partida <= razao
        ):
            acertaram += 1

    return TaxaDeToque(
        valor=acertaram / janelas,
        janelas=janelas,
        janelas_efetivas=efetivas,
        razao_exigida=razao,
        preco_de_hoje=hoje,
        alvo=alvo,
        horizonte_dias=horizonte_dias,
        primeiro_dia=limpa[0][0],
        ultimo_dia=limpa[-1][0],
        direcao=direcao,
    )


def maximo_historico(serie: list[tuple[date, float]]) -> float:
    """O maior preço já registrado. Para os mercados de "nova máxima histórica".

    Vale lembrar do que ele é feito: o máximo do que ESTA série cobre. O WTI do
    FRED começa em 1986 e o pico dele é de 2008; um "recorde histórico" medido
    sobre uma série que começa em 1986 não é o mesmo que sobre uma que começa em
    1900. A janela vai para a tela junto com o número.
    """
    validos = [p for _, p in serie if p == p and p > 0]
    if not validos:
        raise SemAmostra("série sem preço utilizável")
    return max(validos)
