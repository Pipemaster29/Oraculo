"""Polymarket, sem nenhuma chave de API.

Duas casas, as duas públicas e abertas:

- **Gamma** (`gamma-api.polymarket.com`) é o catálogo: pergunta, preço atual,
  volume, data de fim, e — para mercado já fechado — o DESFECHO. Serve página
  por página, com `offset`.
- **CLOB** (`clob.polymarket.com/prices-history`) é a série de preço de um
  token. É ela que permite perguntar "quanto o mercado pedia SETE DIAS ANTES do
  fim?", que é a pergunta da calibragem. Sem ela só se conhece o preço final,
  que num mercado resolvido já é 0 ou 1 e não mede nada.

Nenhuma das duas pede cadastro. Medido em 11/09/2026: um mercado de 2024
devolveu 307 pontos diários de histórico numa requisição.

O `User-Agent` é explícito de propósito. O padrão do `urllib` do Python toma 403
de intermediários que filtram por agente, e esse 403 se parece com "o mercado
não existe" para quem estiver lendo o log depressa.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

AGENTE = "oraculo/0.1 (+https://github.com/Pipemaster29/oraculo)"

# MEDIDO em 11/09/2026: a Gamma devolve 100 itens para `limit=100`, `limit=200` e
# `limit=500`. Ela não recusa o pedido maior, não avisa, não manda cabeçalho de
# página — simplesmente entrega 100.
#
# Isso já quebrou este arquivo uma vez. A paginação parava quando a página vinha
# MENOR que o pedido, o que num teto de 100 real e pedido de 500 acontece na
# primeira volta: "buscando até 2.500 mercados" imprimia "100 vieram da Gamma" e
# seguia medindo calibração sobre 1/25 da amostra, com todos os números com cara
# de certos.
#
# Por isso a parada agora é só na página VAZIA, e o teto real mora aqui.
POR_PAGINA = 100


class FalhaDeLeitura(RuntimeError):
    """A fonte não respondeu.

    Existe para separar as duas coisas que este projeto mais confunde: "a fonte
    disse que não há nada" (lista vazia, resultado legítimo) e "não consegui
    perguntar" (rede, 429, 5xx). A segunda NUNCA pode virar zero rio abaixo.
    """


def _pegar(url: str, parametros: dict[str, Any] | None = None, tentativas: int = 4) -> Any:
    """GET com repetição exponencial. Levanta `FalhaDeLeitura` em vez de devolver vazio."""
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas):
        try:
            resposta = requests.get(
                url,
                params=parametros,
                timeout=30,
                headers={"User-Agent": AGENTE, "Accept": "application/json"},
            )
            # 429 e 5xx são "tente de novo"; 4xx restante é pergunta malfeita e
            # repetir não conserta.
            if resposta.status_code == 429 or resposta.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resposta.status_code}")
            resposta.raise_for_status()
            return resposta.json()
        except Exception as erro:  # noqa: BLE001 — a intenção é justamente agrupar
            ultimo_erro = erro
            if tentativa < tentativas - 1:
                time.sleep(2**tentativa)
    raise FalhaDeLeitura(f"{url} falhou em {tentativas} tentativas: {ultimo_erro}")


def _lista_json(bruto: Any) -> list[Any]:
    """A Gamma manda `outcomes`, `outcomePrices` e `clobTokenIds` como STRING de JSON.

    Ou seja: `'["Yes", "No"]'`, não `["Yes", "No"]`. Tratar como lista direto
    funciona por acidente (uma string é iterável) e devolve caractere por
    caractere.
    """
    if bruto is None:
        return []
    if isinstance(bruto, list):
        return bruto
    try:
        valor = json.loads(bruto)
    except (json.JSONDecodeError, TypeError):
        return []
    return valor if isinstance(valor, list) else []


# MEDIDO em 11/09/2026, varrendo offset de 100 em 100: `offset=2000&limit=100`
# devolve 200, `offset=2010` devolve 422. O corte é `offset + limit <= 2100`.
#
# Ou seja: por esta rota o Polymarket serve no máximo 2.100 mercados por filtro,
# e os de maior volume são os que cabem. Não é escolha nossa e a amostra herda
# esse recorte — o README diz o que isso significa para a calibragem.
TETO_DE_OFFSET = 2100


@dataclass
class Colheita:
    """O que veio E por que parou de vir.

    O segundo campo existe porque as duas frases abaixo produzem exatamente a
    mesma lista e significam coisas opostas:

    - "pedi 3.000 e a fonte só tem 2.100" — a amostra está completa;
    - "pedi 3.000, li 2.100 e a fonte me barrou" — a amostra está TRUNCADA e
      qualquer estatística sobre ela é sobre um recorte que eu não escolhi.

    Já custou caro neste arquivo: a primeira versão parava na página menor que o
    pedido, imprimia "100 vieram da Gamma" para um pedido de 2.500, e a
    calibragem saía medida sobre 1/25 da amostra com todos os números com cara
    de certos.
    """

    mercados: list[dict]
    parada: str

    def __len__(self) -> int:
        return len(self.mercados)

    def __iter__(self):
        return iter(self.mercados)


def _paginar(fechado: bool, teto: int) -> Colheita:
    """Percorre `offset` até juntar `teto` mercados ou a fonte parar de servir.

    Quatro paradas, e cada uma diz uma coisa diferente:

    - **teto atingido** — pedimos o que queríamos e veio;
    - **página vazia** — a fonte disse que acabou. Resultado legítimo;
    - **teto de offset** — a fonte se recusa a paginar mais fundo. TRUNCADO;
    - **página inteira sem id novo** — a fonte está IGNORANDO o `offset`. Sem
      esta parada o laço gira para sempre relendo a página 1, o que num GitHub
      Actions vira uma execução que morre no teto de tempo.
    """
    coletados: list[dict] = []
    vistos: set[str] = set()
    deslocamento = 0
    while len(coletados) < teto:
        if deslocamento + POR_PAGINA > TETO_DE_OFFSET:
            return Colheita(
                coletados[:teto],
                f"teto de offset da Gamma ({TETO_DE_OFFSET}) — amostra TRUNCADA",
            )
        pagina = _pegar(
            f"{GAMMA}/markets",
            {
                "limit": POR_PAGINA,
                "offset": deslocamento,
                "closed": str(fechado).lower(),
                "order": "volumeNum",
                "ascending": "false",
            },
        )
        if not isinstance(pagina, list) or not pagina:
            return Colheita(coletados[:teto], "a fonte disse que acabou")
        novos = [m for m in pagina if str(m.get("id")) not in vistos]
        if not novos:
            return Colheita(coletados[:teto], "a Gamma ignorou o offset — amostra TRUNCADA")
        for mercado in novos:
            vistos.add(str(mercado.get("id")))
        coletados.extend(novos)
        deslocamento += len(pagina)
    return Colheita(coletados[:teto], "teto pedido atingido")


def mercados_abertos(teto: int = 1000) -> Colheita:
    """Mercados ainda em negociação, do maior volume para o menor."""
    return _paginar(fechado=False, teto=teto)


def mercados_resolvidos(teto: int = 1500) -> Colheita:
    """Mercados já fechados, do maior volume para o menor.

    A ordem por volume não é neutra e o README diz por quê: ela mede a
    calibragem de onde há dinheiro, que é onde a tese de "mercado agrega
    informação" deveria valer. Mercado de US$ 200 de volume tem preço de
    ninguém.
    """
    return _paginar(fechado=True, teto=teto)


def desfecho(mercado: dict) -> int | None:
    """1 se o SIM aconteceu, 0 se não, `None` quando não dá para afirmar.

    Depois da resolução a Gamma grava `outcomePrices` como `["1","0"]` ou
    `["0","1"]`. Qualquer outra coisa — mercado invalidado que paga 0,5 para os
    dois lados, resolução em disputa, campo ausente — é `None` e sai da amostra.
    Arredondar 0,5 para algum lado inventaria um acerto ou um erro que não
    houve.
    """
    if not mercado.get("closed"):
        return None
    if mercado.get("umaResolutionStatus") not in (None, "", "resolved"):
        return None
    precos = _lista_json(mercado.get("outcomePrices"))
    if len(precos) != 2:
        return None
    try:
        sim, nao = float(precos[0]), float(precos[1])
    except (TypeError, ValueError):
        return None
    if abs(sim - 1) < 1e-9 and abs(nao) < 1e-9:
        return 1
    if abs(sim) < 1e-9 and abs(nao - 1) < 1e-9:
        return 0
    return None


def preco_atual(mercado: dict) -> float | None:
    """Preço do SIM, que é a probabilidade implícita. `None` se não houver."""
    precos = _lista_json(mercado.get("outcomePrices"))
    if not precos:
        return None
    try:
        valor = float(precos[0])
    except (TypeError, ValueError):
        return None
    # Fora de [0,1] não é preço de contrato binário, é lixo de campo.
    return valor if 0.0 <= valor <= 1.0 else None


def token_do_sim(mercado: dict) -> str | None:
    tokens = _lista_json(mercado.get("clobTokenIds"))
    return str(tokens[0]) if tokens else None


def historico_de_preco(token: str, fidelidade_min: int = 1440) -> list[tuple[int, float]]:
    """Série `(instante unix, preço)` do token, do começo ao fim.

    `fidelidade_min=1440` é um ponto por dia. A calibragem só precisa de um
    ponto por dia — pedir por hora multiplica o peso da resposta por 24 para
    responder a mesma pergunta.
    """
    dados = _pegar(
        f"{CLOB}/prices-history",
        {"market": token, "interval": "max", "fidelity": fidelidade_min},
    )
    pontos = (dados or {}).get("history") or []
    saida: list[tuple[int, float]] = []
    for ponto in pontos:
        try:
            instante, preco = int(ponto["t"]), float(ponto["p"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0.0 <= preco <= 1.0:
            saida.append((instante, preco))
    saida.sort()
    return saida


def preco_antes(serie: list[tuple[int, float]], limite_unix: int) -> float | None:
    """Último preço em `serie` no instante `limite_unix` ou antes dele.

    `None` quando a série inteira começa DEPOIS do limite — mercado que só abriu
    na véspera não tem preço de sete dias antes, e usar o primeiro ponto que
    existe seria usar um preço de outro horizonte e chamá-lo do mesmo.
    """
    achado: float | None = None
    for instante, preco in serie:
        if instante <= limite_unix:
            achado = preco
        else:
            break
    return achado
