"""Mede a calibração do Polymarket sobre mercados já resolvidos.

    python -m scripts.calibrar [--teto 1200] [--volume-minimo 20000]

O caminho:

1. pede à Gamma os mercados FECHADOS, do maior volume para o menor;
2. fica só com os que resolveram limpo — `["1","0"]` ou `["0","1"]`, sem
   invalidação e sem disputa;
3. para cada um, puxa a série de preço do CLOB e lê o preço de 1, 7 e 30 dias
   antes do fim;
4. junta em três amostras e mede cada uma.

O passo 3 é uma requisição por mercado e é o que demora. Oito linhas em
paralelo; mais que isso começa a tomar 429 e a espera exponencial devolve o
tempo economizado.

**Um mercado que falhar no passo 3 sai da amostra e é CONTADO na saída.** Sem
esse número não dá para distinguir "medi 800 mercados" de "tentei 1200 e 400 não
responderam", e as duas frases sustentam confianças muito diferentes.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from oraculo import guardado
from oraculo.calibragem import BANDA_SUSPEITA, banda, medir, viés_favorito_azarao
from oraculo.fontes import polymarket

HORIZONTES = (1, 7, 30)

# Mercado de volume baixo tem preço de ninguém: uma ordem de US$ 50 move a
# cotação inteira, e medir a "sabedoria" disso mede o humor de um apostador. O
# corte é arbitrário e por isso está escrito no rótulo da medição — quem quiser
# outro passa `--volume-minimo`.
VOLUME_MINIMO = 20_000.0


def fim_em_unix(mercado: dict) -> int | None:
    bruto = mercado.get("endDate") or mercado.get("closedTime")
    if not bruto:
        return None
    try:
        quando = datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except ValueError:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return int(quando.timestamp())


def amostrar(mercado: dict) -> dict | None:
    """Devolve `{horizonte: preço}` + desfecho, ou `None` se não der para medir."""
    resultado = polymarket.desfecho(mercado)
    if resultado is None:
        return None
    fim = fim_em_unix(mercado)
    token = polymarket.token_do_sim(mercado)
    if fim is None or token is None:
        return None

    serie = polymarket.historico_de_preco(token)
    if not serie:
        return None

    precos: dict[int, float] = {}
    for dias in HORIZONTES:
        preco = polymarket.preco_antes(serie, fim - dias * 86_400)
        if preco is not None:
            precos[dias] = preco
    if not precos:
        return None

    return {
        "id": str(mercado.get("id")),
        "pergunta": mercado.get("question"),
        "desfecho": resultado,
        "volume": float(mercado.get("volumeNum") or 0.0),
        "precos": precos,
    }


def main() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--teto", type=int, default=1200)
    argumentos.add_argument("--volume-minimo", type=float, default=VOLUME_MINIMO)
    opcoes = argumentos.parse_args()

    print(f"Buscando até {opcoes.teto} mercados resolvidos...", flush=True)
    try:
        colheita = polymarket.mercados_resolvidos(teto=opcoes.teto)
    except polymarket.FalhaDeLeitura as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    mercados = colheita.mercados
    print(f"  {len(mercados)} vieram da Gamma — parou porque: {colheita.parada}", flush=True)

    vistos: set[str] = set()
    candidatos: list[dict] = []
    for mercado in mercados:
        chave = str(mercado.get("conditionId") or mercado.get("id"))
        if chave in vistos:
            continue
        vistos.add(chave)
        if polymarket.desfecho(mercado) is None:
            continue
        if float(mercado.get("volumeNum") or 0.0) < opcoes.volume_minimo:
            continue
        candidatos.append(mercado)
    print(
        f"  {len(candidatos)} resolveram limpo e passaram do volume mínimo "
        f"de US$ {opcoes.volume_minimo:,.0f}",
        flush=True,
    )

    medidos: list[dict] = []
    sem_historico = 0
    with ThreadPoolExecutor(max_workers=8) as piscina:
        tarefas = {piscina.submit(amostrar, m): m for m in candidatos}
        for concluida in as_completed(tarefas):
            try:
                linha = concluida.result()
            except Exception:  # noqa: BLE001 — falha de rede não derruba o lote
                linha = None
            if linha is None:
                sem_historico += 1
            else:
                medidos.append(linha)
            total = len(medidos) + sem_historico
            if total % 100 == 0:
                print(f"  ... {total}/{len(candidatos)}", flush=True)

    print(f"  {len(medidos)} com histórico, {sem_historico} sem", flush=True)
    if not medidos:
        print("ERRO: nenhum mercado mediu. Não gravo nada.", file=sys.stderr)
        return 1

    saida: dict = {
        "volume_minimo": opcoes.volume_minimo,
        "parada_da_colheita": colheita.parada,
        "mercados_pedidos": len(mercados),
        "mercados_candidatos": len(candidatos),
        "mercados_medidos": len(medidos),
        "mercados_sem_historico": sem_historico,
        "horizontes": {},
    }

    print()
    for dias in HORIZONTES:
        amostra = [(m["precos"][dias], m["desfecho"]) for m in medidos if dias in m["precos"]]
        resultado = medir(amostra, horizonte_dias=dias)
        if resultado is None:
            print(f"{dias:>3}d: amostra vazia")
            continue
        vies = viés_favorito_azarao(resultado)
        print(
            f"{dias:>3}d antes do fim | n={resultado.n:<5} "
            f"Brier={resultado.brier:.4f} (climatologia {resultado.brier_da_climatologia:.4f}, "
            f"ganho {resultado.ganho_sobre_climatologia:+.1%}) "
            f"confiab.={resultado.confiabilidade:.4f} resol.={resultado.resolucao:.4f}"
        )
        for faixa in resultado.faixas:
            if faixa.n == 0:
                continue
            marca = "" if faixa.confiavel else "  (n baixo, fora do ajuste)"
            print(
                f"       {faixa.piso:.1f}–{faixa.teto:.1f}  n={faixa.n:<5} "
                f"pediu {faixa.preco_medio:.3f}  aconteceu {faixa.frequencia_real:.3f}  "
                f"erro {faixa.erro:+.3f}{marca}"
            )
        def formatar(valor: float | int | None) -> str:
            return "sem n" if valor is None else f"{valor:+.3f}"

        print(
            f"       azarão (<0,20): erro {formatar(vies['erro_azarao'])} "
            f"(n={vies['n_azarao']}) | "
            f"favorito (>0,80): erro {formatar(vies['erro_favorito'])} "
            f"(n={vies['n_favorito']})"
        )

        faixa_suspeita = banda(resultado, *BANDA_SUSPEITA)
        if faixa_suspeita["z"] is not None:
            print(
                f"       banda {BANDA_SUSPEITA[0]:.2f}–{BANDA_SUSPEITA[1]:.2f}: "
                f"n={faixa_suspeita['n']} pediu {faixa_suspeita['preco_medio']:.3f} "
                f"aconteceu {faixa_suspeita['frequencia_real']:.3f} "
                f"dif {faixa_suspeita['diferenca']:+.3f} z={faixa_suspeita['z']:+.2f} "
                f"(z otimista: mercados do mesmo evento não são independentes)"
            )
        print()

        saida["horizontes"][str(dias)] = {
            "n": resultado.n,
            "taxa_base": resultado.taxa_base,
            "brier": resultado.brier,
            "brier_da_climatologia": resultado.brier_da_climatologia,
                "brier_das_faixas": resultado.brier_das_faixas,
                "ganho_da_precisao_fina": resultado.ganho_da_precisao_fina,
            "ganho_sobre_climatologia": resultado.ganho_sobre_climatologia,
            "confiabilidade": resultado.confiabilidade,
            "resolucao": resultado.resolucao,
            "incerteza": resultado.incerteza,
            "vies_favorito_azarao": vies,
            "banda_suspeita": {
                "piso": BANDA_SUSPEITA[0],
                "teto": BANDA_SUSPEITA[1],
                **faixa_suspeita,
            },
            "faixas": [
                {
                    "piso": f.piso,
                    "teto": f.teto,
                    "n": f.n,
                    "preco_medio": f.preco_medio,
                    "frequencia_real": f.frequencia_real,
                    "erro": f.erro,
                    "confiavel": f.confiavel,
                }
                for f in resultado.faixas
            ],
        }

    caminho = guardado.gravar("calibragem", saida)
    print(f"gravado em {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
