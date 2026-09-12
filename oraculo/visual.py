"""Geometria dos gráficos, em Python puro.

Os cálculos de coordenada moram aqui e não dentro do template por dois motivos:
o Jinja fica sem aritmética (que é onde erro de gráfico se esconde) e estas
funções entram no `scripts/testar.py` sem subir servidor nenhum.

Nada aqui sabe o que é azul. Cor é papel, e papel se resolve com token de CSS no
template; este módulo só devolve onde as coisas ficam.
"""

from __future__ import annotations

from dataclasses import dataclass

# A área de plotagem é quadrada de propósito. Num diagrama de confiabilidade os
# dois eixos são a MESMA grandeza — probabilidade — e a diagonal de 45° é a
# referência que o olho usa. Esticar um dos lados entorta essa diagonal e o
# gráfico passa a sugerir desvio onde não há.
LADO = 320
MARGEM_ESQUERDA = 46
MARGEM_INFERIOR = 38
MARGEM_SUPERIOR = 14
MARGEM_DIREITA = 14

LARGURA = MARGEM_ESQUERDA + LADO + MARGEM_DIREITA
ALTURA = MARGEM_SUPERIOR + LADO + MARGEM_INFERIOR


@dataclass
class Ponto:
    x: float
    y: float
    raio: float
    n: int
    preco: float
    frequencia: float
    rotulo: str
    confiavel: bool


def _x(valor: float) -> float:
    return MARGEM_ESQUERDA + valor * LADO


def _y(valor: float) -> float:
    # SVG cresce para baixo; probabilidade cresce para cima.
    return MARGEM_SUPERIOR + (1.0 - valor) * LADO


def _raio(n: int, maior_n: int) -> float:
    """Área proporcional a `n`, com piso de 4 de raio (8 px de diâmetro).

    Área e não raio: raio proporcional faz um balde com o dobro da amostra
    parecer quatro vezes maior, que é a distorção clássica de gráfico de bolha.
    O piso existe porque marca menor que 8 px não recebe toque de dedo nem
    ponteiro com precisão.
    """
    if maior_n <= 0 or n <= 0:
        return 4.0
    return max(4.0, 4.0 + 7.0 * (n / maior_n) ** 0.5)


def diagrama_de_confiabilidade(faixas: list[dict]) -> dict:
    """Pontos, diagonal e marcas de eixo para o diagrama.

    Faixa com `n == 0` não vira ponto. Desenhá-la no centro do balde com
    frequência zero colocaria um ponto colado no eixo x — que o olho lê como
    "nunca aconteceu" quando o que houve foi "nunca foi perguntado".
    """
    povoadas = [f for f in faixas if int(f.get("n") or 0) > 0]
    maior = max((int(f["n"]) for f in povoadas), default=0)

    pontos = [
        Ponto(
            x=_x(float(f["preco_medio"])),
            y=_y(float(f["frequencia_real"])),
            raio=_raio(int(f["n"]), maior),
            n=int(f["n"]),
            preco=float(f["preco_medio"]),
            frequencia=float(f["frequencia_real"]),
            rotulo=f"{float(f['piso']):.1f}–{float(f['teto']):.1f}",
            confiavel=bool(f.get("confiavel")),
        )
        for f in povoadas
    ]
    pontos.sort(key=lambda p: p.x)

    marcas = [0.0, 0.25, 0.5, 0.75, 1.0]
    return {
        "largura": LARGURA,
        "altura": ALTURA,
        "pontos": pontos,
        "linha": " ".join(f"{p.x:.1f},{p.y:.1f}" for p in pontos),
        "diagonal": {"x1": _x(0), "y1": _y(0), "x2": _x(1), "y2": _y(1)},
        "moldura": {
            "x": MARGEM_ESQUERDA,
            "y": MARGEM_SUPERIOR,
            "lado": LADO,
        },
        "marcas_x": [{"valor": m, "x": _x(m), "y": MARGEM_SUPERIOR + LADO} for m in marcas],
        "marcas_y": [{"valor": m, "y": _y(m), "x": MARGEM_ESQUERDA} for m in marcas],
    }


# --------------------------------------------------------------------------
# A barra de comparação do painel
# --------------------------------------------------------------------------
# Cada linha da tabela compara DOIS números da mesma grandeza (preço e
# taxa-base, ambos probabilidade). O formato certo para isso é o haltere: dois
# pontos numa régua comum, ligados. Duas barras lado a lado convidariam a somar
# o que não se soma, e um gráfico por linha desperdiçaria a régua comum, que é
# justamente o que deixa as linhas comparáveis entre si.

REGUA = 168.0


def haltere(preco: float, taxa_base: float | None) -> dict:
    """Posições na régua de 0 a 100% para o preço e a taxa-base.

    `taxa_base` ausente devolve só o preço, e o template desenha só ele. Não há
    valor de reserva: colocar a marca da história em zero afirmaria "a história
    diz que isto nunca acontece", que é uma leitura, não uma ausência de
    leitura.
    """
    dados: dict = {
        "largura": REGUA,
        "mercado": max(0.0, min(1.0, preco)) * REGUA,
        "historia": None,
        "ligacao": None,
    }
    if taxa_base is None:
        return dados
    historia = max(0.0, min(1.0, taxa_base)) * REGUA
    dados["historia"] = historia
    dados["ligacao"] = {
        "x1": min(dados["mercado"], historia),
        "x2": max(dados["mercado"], historia),
    }
    return dados
