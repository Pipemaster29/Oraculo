"""Ouro e prata pela LBMA, sem nenhuma chave de API.

A London Bullion Market Association **publica o próprio benchmark** — o preço
que o resto do mercado usa como referência — em JSON aberto:

    https://prices.lbma.org.uk/json/gold_pm.json
    https://prices.lbma.org.uk/json/silver.json

Medido em 12/09/2026: ouro com 14.681 leilões desde **1968-04-01** e prata com
14.844 desde **1968-01-02**. Cinquenta e oito anos, da fonte primária.

**Por que não o FRED, que é a fonte de todo o resto daqui.** Ele descontinuou as
séries da LBMA (`GOLDAMGBD228NLBM` responde 404 hoje) e o que sobra em ouro é
`IQ12260`, que é ÍNDICE de preço de importação e não dólar por onça — o último
valor dele é 154,8, contra os US$ 4.386,25 do leilão. Usar um índice para
responder "o ouro chega a US$ 6.000?" compararia duas grandezas diferentes com a
mesma unidade na tela.

**Por que não o Stooq**, que seria o atalho: ele responde com um desafio de
JavaScript por prova de trabalho. Não dá para atender num script, e contorná-lo
seria passar por cima de uma recusa explícita do servidor.

O formato é `[{"d": "1968-04-01", "v": [dólar, libra, euro]}, ...]`. O leilão da
TARDE (`gold_pm`) é o benchmark de referência do ouro; a prata tem um leilão só.
"""

from __future__ import annotations

import time
from datetime import date

import requests

FONTES = {
    "ouro": "https://prices.lbma.org.uk/json/gold_pm.json",
    "prata": "https://prices.lbma.org.uk/json/silver.json",
}

AGENTE = "oraculo/0.1 (+https://github.com/Pipemaster29/Oraculo)"


class FalhaDeLeitura(RuntimeError):
    """Não consegui perguntar. Diferente de "aquele dia não teve leilão"."""


def serie(metal: str, tentativas: int = 4) -> list[tuple[date, float]]:
    """`(dia, dólar por onça)`, ordenado, **só com os dias que têm preço**.

    Medido: 19 das 14.844 linhas da prata vêm com o dólar em `null` — feriado, ou
    leilão sem apuração. Elas são DESCARTADAS e não viram zero: uma prata a US$ 0
    no meio da série produziria uma queda de 100% e uma alta de infinito por
    cento em dois dias seguidos, e a taxa-base de toque leria as duas como
    movimento que aconteceu de verdade.
    """
    if metal not in FONTES:
        raise ValueError(f"metal desconhecido: {metal!r}; use um de {sorted(FONTES)}")

    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            resposta = requests.get(
                FONTES[metal],
                timeout=60,
                headers={"User-Agent": AGENTE, "Accept": "application/json"},
            )
            resposta.raise_for_status()
            bruto = resposta.json()
            break
        except Exception as erro:  # noqa: BLE001
            ultimo_erro = erro
            if tentativa < tentativas - 1:
                time.sleep(2**tentativa)
    else:
        raise FalhaDeLeitura(f"LBMA {metal} falhou: {ultimo_erro}")

    if not isinstance(bruto, list) or not bruto:
        raise FalhaDeLeitura(f"LBMA {metal} devolveu {type(bruto).__name__}, não uma lista")

    leituras: list[tuple[date, float]] = []
    for linha in bruto:
        if not isinstance(linha, dict):
            continue
        valores = linha.get("v")
        if not isinstance(valores, list) or not valores or valores[0] is None:
            continue
        try:
            dia = date.fromisoformat(str(linha["d"]))
            dolar = float(valores[0])
        except (KeyError, TypeError, ValueError):
            continue
        if dolar > 0:
            leituras.append((dia, dolar))

    if not leituras:
        raise FalhaDeLeitura(f"LBMA {metal}: nenhuma linha com preço em dólar")

    leituras.sort()
    return leituras
