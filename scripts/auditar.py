"""Confere as invariantes de tudo que está em `data/`.

    python -m scripts.auditar

Sai com código diferente de zero quando alguma quebra, e é por isso que ele roda
no Actions ANTES do commit: sem ele, uma fonte que muda de formato grava um JSON
vazio ou com lixo, o commit passa, a Vercel publica, e a página mostra o lixo
com cara de medição.

`scripts/testar.py` e este arquivo respondem perguntas diferentes e os dois
precisam existir. Aquele pergunta "o código está certo?" com entradas
inventadas; este pergunta "o dado que acabou de ser produzido faz sentido?" com
o dado real. Código certo alimentado por uma fonte que mudou produz arquivo
errado sem erro nenhum.
"""

from __future__ import annotations

import math

from oraculo import guardado

_problemas: list[str] = []
_avisos: list[str] = []


def exigir(condicao: bool, descricao: str) -> None:
    if not condicao:
        _problemas.append(descricao)


def avisar(condicao: bool, descricao: str) -> None:
    if not condicao:
        _avisos.append(descricao)


def _finito_entre(valor, piso: float, teto: float) -> bool:
    return (
        isinstance(valor, (int, float))
        and not isinstance(valor, bool)
        and math.isfinite(valor)
        and piso - 1e-9 <= valor <= teto + 1e-9
    )


def auditar_calibragem() -> None:
    bloco = guardado.ler("calibragem")
    if bloco is None:
        _problemas.append("data/calibragem.json não existe ou não é JSON válido")
        return

    print("data/calibragem.json")
    exigir(bool(bloco.get("gerado_em")), "calibragem sem carimbo de hora")

    medidos = bloco.get("mercados_medidos") or 0
    candidatos = bloco.get("mercados_candidatos") or 0
    exigir(medidos > 0, "calibragem não mediu nenhum mercado")
    exigir(
        medidos <= candidatos,
        f"calibragem mediu {medidos} de {candidatos} candidatos — mediu mais do que tinha",
    )

    # Um lote em que quase tudo falhou na leitura do histórico produz uma
    # calibragem sobre a minoria que respondeu, e essa minoria não é sorteada:
    # são os mercados com série longa, ou seja os mais antigos e mais líquidos.
    sem_historico = bloco.get("mercados_sem_historico") or 0
    if candidatos:
        avisar(
            sem_historico / candidatos < 0.25,
            f"{sem_historico} de {candidatos} candidatos sem histórico "
            f"({sem_historico / candidatos:.0%}) — a amostra está enviesada para quem responde",
        )

    horizontes = bloco.get("horizontes") or {}
    exigir(bool(horizontes), "calibragem sem nenhum horizonte")

    for chave, dados in horizontes.items():
        rotulo = f"calibragem[{chave}d]"
        exigir(_finito_entre(dados.get("brier"), 0, 1), f"{rotulo}: Brier fora de [0,1]")
        exigir(
            _finito_entre(dados.get("taxa_base"), 0, 1),
            f"{rotulo}: taxa-base fora de [0,1]",
        )
        exigir(int(dados.get("n") or 0) > 0, f"{rotulo}: n zerado")

        faixas = dados.get("faixas") or []
        exigir(len(faixas) == 10, f"{rotulo}: esperava 10 faixas, veio {len(faixas)}")

        soma = sum(int(f.get("n") or 0) for f in faixas)
        exigir(
            soma == int(dados.get("n") or -1),
            f"{rotulo}: as faixas somam {soma} mas n é {dados.get('n')} — "
            "alguma observação caiu fora de todos os baldes",
        )

        for faixa in faixas:
            piso = faixa.get("piso")
            exigir(
                _finito_entre(faixa.get("frequencia_real"), 0, 1),
                f"{rotulo} faixa {piso}: frequência fora de [0,1]",
            )
            if int(faixa.get("n") or 0) > 0:
                exigir(
                    _finito_entre(faixa.get("preco_medio"), faixa["piso"], faixa["teto"]),
                    f"{rotulo} faixa {piso}: preço médio fora da própria faixa",
                )

        # Decomposição de Murphy: confiabilidade − resolução + incerteza.
        # Se ela não fechar, uma das três contas está sobre uma amostra
        # diferente das outras — e nenhum dos quatro números na tela vale.
        #
        # A conferência é contra `brier_das_faixas` e NÃO contra `brier`. A
        # identidade só vale quando cada faixa tem um único valor de previsão;
        # com preço contínuo em baldes de dez pontos sobra a variação dentro do
        # balde. Quando esta conferência era contra `brier` ela quebrava nos três
        # horizontes por ~0,0007 — erro pequeno o bastante para tentar a gente a
        # afrouxar a tolerância, que teria escondido a explicação em vez de
        # registrá-la.
        esperado = (
            float(dados.get("confiabilidade", 0))
            - float(dados.get("resolucao", 0))
            + float(dados.get("incerteza", 0))
        )
        exigir(
            abs(esperado - float(dados.get("brier_das_faixas", -1))) < 1e-9,
            f"{rotulo}: a decomposição de Murphy não fecha "
            f"({esperado:.9f} contra Brier das faixas {dados.get('brier_das_faixas')})",
        )

    print(f"  {len(horizontes)} horizontes, {medidos} mercados medidos")


def auditar_painel() -> None:
    bloco = guardado.ler("painel")
    if bloco is None:
        _problemas.append("data/painel.json não existe ou não é JSON válido")
        return

    print("data/painel.json")
    exigir(bool(bloco.get("gerado_em")), "painel sem carimbo de hora")
    exigir(int(bloco.get("mercados_lidos") or 0) > 0, "painel não leu nenhum mercado")

    linhas = bloco.get("linhas") or []
    exigir(bool(linhas), "painel sem nenhuma linha — nenhum mercado casou com o catálogo")

    for linha in linhas:
        rotulo = f"painel[{str(linha.get('pergunta'))[:40]}]"
        exigir(_finito_entre(linha.get("preco"), 0, 1), f"{rotulo}: preço fora de [0,1]")

        taxa = linha.get("taxa_base")
        if taxa is not None:
            exigir(_finito_entre(taxa, 0, 1), f"{rotulo}: taxa-base fora de [0,1]")
            # A distância é derivada. Se ela não bater com a subtração, os dois
            # números da tela vêm de leituras diferentes.
            exigir(
                abs(float(linha["preco"]) - float(taxa) - float(linha.get("distancia", 0))) < 1e-9,
                f"{rotulo}: distância não é preço menos taxa-base",
            )
            exigir(
                int(linha.get("taxa_base_n") or 0) > 0,
                f"{rotulo}: tem taxa-base com n zerado — n zero não mede nada",
            )
        else:
            # A regra do projeto: sem leitura, o campo é None e a página escreve
            # travessão. Zero seria uma afirmação ("nunca acontece") disfarçada
            # de ausência.
            exigir(
                linha.get("distancia") is None,
                f"{rotulo}: sem taxa-base mas com distância — de onde veio?",
            )
            exigir(
                bool(linha.get("taxa_base_falha")),
                f"{rotulo}: sem taxa-base e sem motivo escrito",
            )

        ajustado = linha.get("preco_ajustado")
        if ajustado is not None:
            exigir(_finito_entre(ajustado, 0, 1), f"{rotulo}: preço ajustado fora de [0,1]")

    idade = guardado.idade_em_minutos(bloco)
    if idade is not None:
        avisar(idade < 24 * 60, f"painel com {idade / 60:.0f} h — o Actions parou de rodar?")

    print(f"  {len(linhas)} linhas, {len(bloco.get('sem_familia') or [])} órfãos")


def main() -> int:
    auditar_calibragem()
    auditar_painel()

    print()
    for aviso in _avisos:
        print(f"  AVISO   {aviso}")
    for problema in _problemas:
        print(f"  QUEBRA  {problema}")

    if _problemas:
        print(f"\n{len(_problemas)} invariante(s) quebrada(s). Não commite isto.")
        return 1
    print(f"\ninvariantes de acordo{f' ({len(_avisos)} aviso(s))' if _avisos else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
