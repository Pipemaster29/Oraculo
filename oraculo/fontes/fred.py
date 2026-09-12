"""FRED, sem nenhuma chave de API.

A API oficial do FRED (`api.stlouisfed.org`) pede chave. O gerador de gráfico do
próprio site não pede:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE

Devolve a série inteira em CSV, sem cadastro e sem cota publicada. Medido em
11/09/2026: `UNRATE` volta desde 1948-01-01.

É a mesma série que a API serve — muda o envelope, não o dado. Ficar na API
oficial custaria a restrição de projeto que organiza tudo aqui.
"""

from __future__ import annotations

import csv
import io
import time
from datetime import date

import requests

CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
AGENTE = "oraculo/0.1 (+https://github.com/Pipemaster29/Oraculo)"


class FalhaDeLeitura(RuntimeError):
    """Não consegui perguntar. Diferente de "a série não tem esse ponto"."""


# `Observacao.valor` é `None` quando o FRED grava "." — feriado, série ainda não
# publicada, revisão em curso. Virar 0.0 aqui colocaria desemprego zero em 1948 e
# a taxa-base leria isso como um mês bom.
Observacao = tuple[date, float | None]


def serie(identificador: str, tentativas: int = 4) -> list[Observacao]:
    """A série inteira do FRED, ordenada por data."""
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            resposta = requests.get(
                CSV,
                params={"id": identificador},
                timeout=40,
                headers={"User-Agent": AGENTE},
            )
            resposta.raise_for_status()
            texto = resposta.text
            break
        except Exception as erro:  # noqa: BLE001
            ultimo_erro = erro
            if tentativa < tentativas - 1:
                time.sleep(2**tentativa)
    else:
        raise FalhaDeLeitura(f"FRED {identificador} falhou: {ultimo_erro}")

    leitor = csv.reader(io.StringIO(texto))
    try:
        cabecalho = next(leitor)
    except StopIteration as vazio:
        raise FalhaDeLeitura(f"FRED {identificador} veio sem cabeçalho") from vazio

    # O CSV tem duas colunas: data e valor. O nome da primeira já foi
    # `DATE` e hoje é `observation_date`; o da segunda é o identificador da
    # série. Fixar qualquer um dos dois quebra sozinho quando o FRED renomear,
    # então o que vale é a POSIÇÃO.
    if len(cabecalho) < 2:
        raise FalhaDeLeitura(f"FRED {identificador}: cabeçalho {cabecalho!r} não tem duas colunas")

    observacoes: list[Observacao] = []
    for linha in leitor:
        if len(linha) < 2 or not linha[0].strip():
            continue
        try:
            dia = date.fromisoformat(linha[0].strip())
        except ValueError:
            continue
        cru = linha[1].strip()
        if cru in ("", "."):
            observacoes.append((dia, None))
            continue
        try:
            observacoes.append((dia, float(cru)))
        except ValueError:
            observacoes.append((dia, None))

    if not observacoes:
        raise FalhaDeLeitura(f"FRED {identificador} devolveu CSV sem nenhuma linha de dado")

    observacoes.sort(key=lambda o: o[0])
    return observacoes


def variacao_percentual(observacoes: list[Observacao]) -> list[tuple[date, float]]:
    """Variação de um período para o seguinte, em PONTOS PERCENTUAIS (5,0 = 5%).

    Só emite o par quando os DOIS pontos existem. Um buraco no meio não vira uma
    variação sobre o vizinho de dois períodos atrás disfarçada de variação de um
    período.
    """
    saida: list[tuple[date, float]] = []
    for (_, anterior), (dia, atual) in zip(observacoes, observacoes[1:]):
        if anterior is None or atual is None or anterior == 0:
            continue
        saida.append((dia, (atual / anterior - 1.0) * 100.0))
    return saida
