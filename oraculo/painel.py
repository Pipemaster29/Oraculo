"""Uma linha por mercado: o que o preço diz, o que a história diz, o que a calibragem corrige.

As três colunas respondem perguntas diferentes e a página tem de deixar isso
claro, porque juntá-las é a forma mais fácil de mentir com este projeto:

- **preço** — o que o mercado cobra hoje. É informação de verdade, com dinheiro
  atrás, e sabe coisas que nenhuma das outras duas sabe;
- **taxa-base** — com que frequência isto aconteceu num período comparável. NÃO
  é previsão: não sabe nada sobre 2026 em particular;
- **ajustado** — o preço passado pela curva de confiabilidade medida em
  `calibragem.py`. Só existe onde a faixa tem n suficiente.

A **distância** entre preço e taxa-base é o número que a página ordena, e ela
também não é sinal de compra. Distância grande quer dizer "o mercado acha este
período muito diferente de um período típico" — o que pode ser porque o mercado
sabe de algo (o normal) ou porque está errado (o raro). O Oráculo não distingue
os dois casos e não finge distinguir.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from oraculo import catalogo
from oraculo.calibragem import Calibragem
from oraculo.fontes import polymarket


@dataclass
class Linha:
    id: str
    pergunta: str
    url: str
    volume: float
    liquidez: float
    fim: str | None
    dias_para_o_fim: float | None

    preco: float

    familia: str | None
    taxa_base: float | None
    taxa_base_n: int | None
    taxa_base_janela: str | None
    taxa_base_descricao: str | None
    taxa_base_ressalva: str | None
    taxa_base_series: list[str] | None
    taxa_base_falha: str | None

    preco_ajustado: float | None
    distancia: float | None


def _fim_em_dias(mercado: dict) -> tuple[str | None, float | None]:
    bruto = mercado.get("endDate")
    if not bruto:
        return None, None
    try:
        quando = datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    dias = (quando - datetime.now(timezone.utc)).total_seconds() / 86_400
    return quando.isoformat(), dias


def montar(
    mercados: list[dict],
    calibragem: Calibragem | None = None,
) -> tuple[list[Linha], list[dict]]:
    """Devolve `(linhas com taxa-base, mercados reconhecidos como econômicos sem família)`.

    A segunda lista é o que falta no catálogo, e existir na saída é de propósito:
    sem ela, um mercado que o Oráculo deveria cobrir e não cobre simplesmente
    some da tela, indistinguível de um mercado que não existe.
    """
    linhas: list[Linha] = []
    orfaos: list[dict] = []

    for mercado in mercados:
        pergunta = mercado.get("question") or ""
        preco = polymarket.preco_atual(mercado)
        if preco is None:
            continue

        # Mercado já vencido ainda aparece como aberto na Gamma por algumas
        # horas, com preço colado em 0 ou 1. Colocá-lo na tela ao lado de uma
        # taxa-base é comparar uma resposta com uma pergunta.
        fim_iso, dias = _fim_em_dias(mercado)
        if dias is not None and dias <= 0:
            continue

        explicacao = catalogo.explicar(pergunta)
        if explicacao is None:
            if _parece_economia(pergunta):
                orfaos.append(
                    {
                        "id": str(mercado.get("id")),
                        "pergunta": pergunta,
                        "volume": float(mercado.get("volumeNum") or 0.0),
                    }
                )
            continue

        familia, taxa, falha = explicacao
        ajustado = calibragem.ajustar(preco) if calibragem else None
        distancia = (preco - taxa.valor) if taxa else None

        linhas.append(
            Linha(
                id=str(mercado.get("id")),
                pergunta=pergunta,
                url=f"https://polymarket.com/event/{mercado.get('slug') or ''}",
                volume=float(mercado.get("volumeNum") or 0.0),
                liquidez=float(mercado.get("liquidityNum") or mercado.get("liquidity") or 0.0),
                fim=fim_iso,
                dias_para_o_fim=dias,
                preco=preco,
                familia=familia.nome,
                taxa_base=taxa.valor if taxa else None,
                taxa_base_n=taxa.n if taxa else None,
                taxa_base_janela=taxa.janela if taxa else None,
                taxa_base_descricao=taxa.descricao if taxa else None,
                taxa_base_ressalva=taxa.ressalva if taxa else None,
                taxa_base_series=taxa.series if taxa else None,
                taxa_base_falha=falha or None,
                preco_ajustado=ajustado,
                distancia=distancia,
            )
        )

    # Ordena pela distância, do maior desacordo com a história para o menor.
    # `None` (taxa-base que não leu) vai para o fim em vez de virar zero, que o
    # colocaria no meio da tabela parecendo "mercado de acordo com a história".
    linhas.sort(key=lambda linha: (linha.distancia is None, -abs(linha.distancia or 0.0)))
    orfaos.sort(key=lambda o: -o["volume"])
    return linhas, orfaos


# O filtro de "isto tem cara de economia" é largo de propósito: ele não decide
# nada, só alimenta a lista do que o catálogo ainda não cobre. Errar para mais
# custa uma linha a conferir; errar para menos esconde um buraco.
#
# **As fronteiras de palavra não são enfeite.** A primeira versão testava
# `chave in pergunta.lower()`, e a lista de órfãos veio com "Communist Party of
# the Russian FEDeration" (por `fed`) e "PhiliPPInes military clash" (por `ppi`).
# Sigla de três letras cabe dentro de meio dicionário; sem `\b` este filtro
# encontra economia em qualquer lugar.
_ECONOMIA = re.compile(
    r"\b("
    r"fed|fomc|powell|interest rates?|federal funds|"
    r"inflation|cpi|ppi|pce|"
    r"recession|unemployment|jobless|payrolls?|jobs report|"
    r"gdp|treasury|yields?"
    r")\b",
    re.I,
)


def _parece_economia(pergunta: str) -> bool:
    return bool(_ECONOMIA.search(pergunta))


def como_dicionario(linha: Linha) -> dict:
    return asdict(linha)
