"""Monta `data/painel.json`: os mercados abertos, com taxa-base e ajuste.

    python -m scripts.montar [--teto 2100]

Lê a calibragem que `scripts/calibrar.py` já gravou, em vez de recalculá-la. São
relógios diferentes de propósito: o preço de um mercado aberto muda de minuto em
minuto, e a calibragem sobre dois mil mercados resolvidos muda de mês em mês.
Refazer a segunda a cada montagem gastaria duas mil requisições para mudar a
terceira casa decimal.

**Se a calibragem não existir, o painel é montado sem a coluna de ajuste** e diz
isso. Não é erro: é a coluna informando que nunca foi medida.
"""

from __future__ import annotations

import argparse
import sys

from oraculo import guardado, painel
from oraculo.calibragem import Calibragem, Faixa
from oraculo.fontes import polymarket


def calibragem_guardada(horizonte: int = 7) -> Calibragem | None:
    """Remonta a `Calibragem` do horizonte pedido a partir de `data/calibragem.json`.

    O horizonte de 7 dias é o padrão porque é o que o projeto trata como
    "previsão". O de 1 dia mede o mercado lendo o jornal e infla o acerto; o de
    30 dias tem amostra menor porque muito mercado do Polymarket nem existe
    trinta dias antes de resolver.
    """
    bloco = guardado.ler("calibragem")
    if not bloco:
        return None
    dados = (bloco.get("horizontes") or {}).get(str(horizonte))
    if not dados:
        return None
    return Calibragem(
        horizonte_dias=horizonte,
        n=int(dados["n"]),
        taxa_base=float(dados["taxa_base"]),
        brier=float(dados["brier"]),
        brier_da_climatologia=float(dados["brier_da_climatologia"]),
        brier_das_faixas=float(dados["brier_das_faixas"]),
        confiabilidade=float(dados["confiabilidade"]),
        resolucao=float(dados["resolucao"]),
        incerteza=float(dados["incerteza"]),
        faixas=[
            Faixa(
                piso=float(f["piso"]),
                teto=float(f["teto"]),
                n=int(f["n"]),
                preco_medio=float(f["preco_medio"]),
                frequencia_real=float(f["frequencia_real"]),
            )
            for f in dados.get("faixas", [])
        ],
    )


def main() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--teto", type=int, default=2100)
    argumentos.add_argument("--horizonte", type=int, default=7)
    opcoes = argumentos.parse_args()

    calibragem = calibragem_guardada(opcoes.horizonte)
    if calibragem is None:
        print(
            f"AVISO: sem calibragem de {opcoes.horizonte}d em data/calibragem.json. "
            "O painel sai sem a coluna de ajuste.",
            file=sys.stderr,
        )

    print(f"Buscando até {opcoes.teto} mercados abertos...", flush=True)
    try:
        colheita = polymarket.mercados_abertos(teto=opcoes.teto)
    except polymarket.FalhaDeLeitura as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    print(f"  {len(colheita)} vieram — parou porque: {colheita.parada}", flush=True)

    linhas, orfaos = painel.montar(colheita.mercados, calibragem)
    print(f"  {len(linhas)} com taxa-base, {len(orfaos)} econômicos sem família no catálogo")
    print()

    for linha in linhas:
        base = "—" if linha.taxa_base is None else f"{linha.taxa_base:.1%}"
        ajustado = "—" if linha.preco_ajustado is None else f"{linha.preco_ajustado:.1%}"
        distancia = "—" if linha.distancia is None else f"{linha.distancia:+.1%}"
        print(
            f"  {linha.preco:6.1%} mercado | {base:>7} história | {ajustado:>7} ajustado "
            f"| {distancia:>7} dist | {linha.pergunta[:64]}"
        )

    if orfaos:
        print("\n  sem família no catálogo (candidatos a estender `oraculo/catalogo.py`):")
        for orfao in orfaos[:15]:
            print(f"    US$ {orfao['volume']:>12,.0f}  {orfao['pergunta'][:78]}")

    caminho = guardado.gravar(
        "painel",
        {
            "horizonte_da_calibragem": opcoes.horizonte if calibragem else None,
            "parada_da_colheita": colheita.parada,
            "mercados_lidos": len(colheita),
            "linhas": [painel.como_dicionario(linha) for linha in linhas],
            "sem_familia": orfaos,
        },
    )
    print(f"\ngravado em {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
