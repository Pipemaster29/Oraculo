"""Número em convenção brasileira: ponto no milhar, vírgula no decimal.

Existe porque a forma óbvia de fazer isso já quebrou este projeto **duas vezes**,
das duas por `.replace(".", ",")` aplicado a uma frase inteira em vez de a um
número:

1. `f"{x:+.1f} p.p.".replace(".", ",")` publicou **"+54,7 p,p,"** na tela — o
   literal "p.p." tem dois pontos e virou dois erros de digitação.
2. Depois, na descrição de uma taxa-base de preço, a troca em cadeia
   `.replace(",", "X").replace(".", ",").replace("X", ".")` passou por cima de um
   rótulo que JÁ estava convertido e devolveu **"US$ 45,000"** para quarenta e
   cinco mil, além de trocar por pontos as vírgulas da frase em volta.

A lição das duas é a mesma: **a conversão é uma propriedade do número, não do
texto que o cerca.** Converta o número, depois monte a frase. Nunca o contrário.
"""

from __future__ import annotations


def br(valor: float | int | None, casas: int = 2, sinal: bool = False) -> str:
    """`1234567.5` → `"1.234.567,50"`. `None` e `NaN` viram travessão.

    O travessão e não "0": a regra do projeto inteiro é que ausência de leitura
    nunca vira um número na tela.
    """
    if valor is None or valor != valor:
        return "—"
    formato = f"{{:{'+' if sinal else ''},.{casas}f}}"
    # O Python formata em convenção americana — vírgula no milhar, ponto no
    # decimal. A troca é feita de uma vez, com um marcador no meio, e SÓ sobre
    # este número: a string que sai daqui já está pronta e nunca deve passar por
    # outro `.replace` rio abaixo.
    return formato.format(valor).replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def dinheiro(valor: float | None, casas: int | None = None) -> str:
    """`"US$ 45.000"`. Sem casas decimais quando o número é grande e redondo.

    `casas=None` decide sozinho: acima de mil, centavo é ruído visual num painel
    que compara ordens de grandeza; abaixo, centavo é informação (o petróleo a
    US$ 97,26 e a US$ 97 são leituras diferentes).
    """
    if valor is None or valor != valor:
        return "—"
    if casas is None:
        casas = 0 if abs(valor) >= 1000 else 2
    return f"US$ {br(valor, casas)}"


def porcento(fracao: float | None, casas: int = 1, sinal: bool = False) -> str:
    """`0.258` → `"25,8%"`. A entrada é FRAÇÃO, não já multiplicada por cem."""
    if fracao is None or fracao != fracao:
        return "—"
    return br(fracao * 100, casas, sinal) + "%"
