"""O mercado é calibrado? A pergunta que sustenta ou derruba tudo o resto.

Um preço de contrato binário É uma probabilidade: pagar US$ 0,70 por um papel
que vale US$ 1 se o evento acontecer é dizer 70%. Calibração é conferir isso
contra o mundo: **das vezes em que o mercado pediu 0,70, o evento aconteceu em
70% delas?**

A medida não precisa de nenhum modelo nosso. Não é "eu acho que o mercado erra",
é aritmética sobre mercados já resolvidos, cujo desfecho é público e conhecido.
Por isso ela vem PRIMEIRO: se o Polymarket for bem calibrado, o preço dele já é
a melhor previsão disponível e qualquer número que o Oráculo colocasse do lado
seria enfeite. Se não for, o desvio é a única coisa aqui que vale alguma coisa.

**O horizonte faz parte da medida e não pode ficar implícito.** O preço na
véspera de um mercado resolvido é quase 0 ou quase 1 e acerta quase sempre; isso
não é previsão, é o mercado lendo o jornal. A calibragem séria pergunta pelo
preço de SETE ou TRINTA dias antes do fim. O `scripts/calibrar.py` mede os três
horizontes lado a lado justamente para esse efeito ficar visível em vez de virar
propaganda.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Dez faixas de dez pontos percentuais. Faixa mais estreita divide a amostra até
# não sobrar n para afirmar nada; mais larga mistura 0,05 com 0,20, que é
# exatamente onde o viés favorito-azarão vive.
LARGURA_DA_FAIXA = 0.10

# Abaixo disto a frequência observada de uma faixa é ruído: com n = 10, um único
# desfecho move a frequência em 10 pontos percentuais. A faixa continua a
# aparecer na tabela, com o n do lado, mas não entra no ajuste.
N_MINIMO_PARA_AJUSTAR = 30


@dataclass
class Faixa:
    """Uma faixa de preço e o que de fato aconteceu dentro dela."""

    piso: float
    teto: float
    n: int
    preco_medio: float
    frequencia_real: float

    @property
    def erro(self) -> float:
        """Positivo = o mercado pediu MENOS do que o mundo entregou (azarão barato)."""
        return self.frequencia_real - self.preco_medio

    @property
    def confiavel(self) -> bool:
        return self.n >= N_MINIMO_PARA_AJUSTAR


@dataclass
class Calibragem:
    """O retrato completo de uma amostra `(preço, desfecho)`."""

    horizonte_dias: int
    n: int
    taxa_base: float
    brier: float
    brier_da_climatologia: float
    # Brier calculado como se cada mercado tivesse sido precificado pela MÉDIA da
    # faixa dele, e não pelo próprio preço.
    #
    # Existe porque a decomposição de Murphy (Brier = confiabilidade − resolução
    # + incerteza) só fecha exatamente quando cada faixa tem um único valor de
    # previsão. Com preço contínuo jogado em baldes de dez pontos, sobra a
    # variação DENTRO do balde, e a identidade erra por pouco: medido em
    # 11/09/2026, 0,0860 contra 0,0841 no horizonte de 7 dias.
    #
    # A saída errada seria afrouxar a conferência até o erro caber. A certa é
    # nomear o número contra o qual a identidade fecha de verdade — e a
    # diferença entre os dois vira informação em vez de resíduo: é quanto o
    # mercado ganha por precificar 0,37 em vez de "algo entre 0,3 e 0,4".
    brier_das_faixas: float
    confiabilidade: float
    resolucao: float
    incerteza: float
    faixas: list[Faixa] = field(default_factory=list)

    @property
    def ganho_da_precisao_fina(self) -> float:
        """Quanto o preço exato bate o preço arredondado para a faixa."""
        return self.brier_das_faixas - self.brier

    @property
    def ganho_sobre_climatologia(self) -> float:
        """Brier skill score. 0 = não sabe mais que "chuto a taxa-base sempre"; 1 = perfeito.

        A climatologia é uma referência dura de propósito. Um mercado que só
        soubesse que recessão é rara já bateria um chute de 50%; bater a taxa-base
        é que exige saber alguma coisa sobre ESTE evento.
        """
        if self.brier_da_climatologia <= 0:
            return 0.0
        return 1.0 - self.brier / self.brier_da_climatologia

    def ajustar(self, preco: float) -> float | None:
        """Mapeia um preço de hoje pela curva medida. `None` onde não há n para afirmar.

        Devolver o próprio preço quando a faixa é rala pareceria "sem ajuste" e
        seria indistinguível de "medi e deu igual". São coisas diferentes e a
        página mostra as duas diferentes.
        """
        if not 0.0 <= preco <= 1.0:
            return None
        for faixa in self.faixas:
            if faixa.piso <= preco < faixa.teto or (preco == 1.0 and faixa.teto == 1.0):
                if not faixa.confiavel:
                    return None
                return min(1.0, max(0.0, preco + faixa.erro))
        return None


def medir(amostra: list[tuple[float, int]], horizonte_dias: int) -> Calibragem | None:
    """`amostra` é uma lista de `(preço no horizonte, desfecho 0 ou 1)`.

    Devolve `None` para amostra vazia. Zero mercados medidos não é calibragem
    perfeita nem péssima — é ausência de medição, e tem de viajar como tal até a
    tela.
    """
    limpa = [
        (preco, desfecho)
        for preco, desfecho in amostra
        # `NaN <= 0` e `NaN >= 0` são AMBOS falsos, então um guard escrito como
        # `if preco < 0: continue` deixa NaN passar inteiro.
        if preco == preco and 0.0 <= preco <= 1.0 and desfecho in (0, 1)
    ]
    if not limpa:
        return None

    n = len(limpa)
    taxa_base = sum(desfecho for _, desfecho in limpa) / n

    brier = sum((preco - desfecho) ** 2 for preco, desfecho in limpa) / n
    brier_climatologia = sum((taxa_base - desfecho) ** 2 for _, desfecho in limpa) / n

    quantidade = int(round(1 / LARGURA_DA_FAIXA))
    baldes: list[list[tuple[float, int]]] = [[] for _ in range(quantidade)]
    for preco, desfecho in limpa:
        indice = min(quantidade - 1, int(preco / LARGURA_DA_FAIXA))
        baldes[indice].append((preco, desfecho))

    faixas: list[Faixa] = []
    confiabilidade = 0.0
    resolucao = 0.0
    for indice, balde in enumerate(baldes):
        piso = indice * LARGURA_DA_FAIXA
        teto = piso + LARGURA_DA_FAIXA
        if not balde:
            faixas.append(Faixa(piso, teto, 0, (piso + teto) / 2, 0.0))
            continue
        n_faixa = len(balde)
        preco_medio = sum(p for p, _ in balde) / n_faixa
        frequencia = sum(d for _, d in balde) / n_faixa
        faixas.append(Faixa(piso, teto, n_faixa, preco_medio, frequencia))
        # Decomposição de Murphy: Brier = confiabilidade − resolução + incerteza.
        # Vale a pena separar porque as duas metades respondem a perguntas
        # diferentes: confiabilidade é "o preço é honesto?" e resolução é "o
        # preço se compromete?". Um mercado que responde a taxa-base para tudo
        # tem confiabilidade perfeita e resolução zero — não erra nunca e não
        # serve para nada.
        confiabilidade += n_faixa * (preco_medio - frequencia) ** 2
        resolucao += n_faixa * (frequencia - taxa_base) ** 2

    confiabilidade /= n
    resolucao /= n
    incerteza = taxa_base * (1 - taxa_base)

    return Calibragem(
        horizonte_dias=horizonte_dias,
        n=n,
        taxa_base=taxa_base,
        brier=brier,
        brier_da_climatologia=brier_climatologia,
        # Por construção, e o auditor confere: este é o Brier que a decomposição
        # de Murphy reconstrói exatamente.
        brier_das_faixas=confiabilidade - resolucao + incerteza,
        confiabilidade=confiabilidade,
        resolucao=resolucao,
        incerteza=incerteza,
        faixas=faixas,
    )


def banda(calibragem: Calibragem, piso: float, teto: float) -> dict[str, float | int | None]:
    """Junta as faixas dentro de `[piso, teto)` e testa se o desvio passa do ruído.

    `z` é a diferença em erros-padrão binomiais. |z| acima de 2 é o costume para
    "provavelmente não é sorte".

    **E o `z` daqui é OTIMISTA, por um motivo que não dá para consertar com mais
    amostra.** O teste binomial supõe desfechos independentes, e os mercados do
    Polymarket não são: um evento de múltiplas opções ("quem vence?" com
    cinquenta nomes) vira cinquenta mercados binários que resolvem JUNTOS — um
    "sim" e quarenta e nove "não", amarrados pela mesma notícia. O n efetivo é o
    número de EVENTOS, não o de mercados, e é bem menor que o que entra nesta
    conta.

    Por isso este número não é conclusão, é filtro: serve para descartar o que
    claramente é ruído, não para promover o resto a descoberta.
    """
    dentro = [f for f in calibragem.faixas if f.piso >= piso - 1e-9 and f.teto <= teto + 1e-9]
    n = sum(f.n for f in dentro)
    if n < N_MINIMO_PARA_AJUSTAR:
        return {"n": n, "preco_medio": None, "frequencia_real": None,
                "diferenca": None, "erro_padrao": None, "z": None}

    preco = sum(f.preco_medio * f.n for f in dentro) / n
    real = sum(f.frequencia_real * f.n for f in dentro) / n
    diferenca = real - preco
    variancia = preco * (1 - preco)
    if variancia <= 0:
        return {"n": n, "preco_medio": preco, "frequencia_real": real,
                "diferenca": diferenca, "erro_padrao": None, "z": None}
    erro_padrao = (variancia / n) ** 0.5
    return {
        "n": n,
        "preco_medio": preco,
        "frequencia_real": real,
        "diferenca": diferenca,
        "erro_padrao": erro_padrao,
        "z": diferenca / erro_padrao,
    }


# A banda 0,10–0,40 não foi escolhida antes de olhar, e dizer isso importa:
# ela saiu de ver o erro apontar para o MESMO lado nas três faixas e nos três
# horizontes medidos. Escolher a janela depois de ver os dados infla qualquer
# teste feito sobre ela — é o mesmo defeito que o `README` do btc-moon descreve
# em "a janela de medição era outra".
#
# O que salva parcialmente este caso é a repetição: a banda separa na mesma
# direção em 1, 7 e 30 dias, que são amostras com sobreposição mas não iguais.
# O que NÃO salva é a dependência entre mercados do mesmo evento. Trate como
# hipótese para a próxima medição, não como achado.
BANDA_SUSPEITA = (0.10, 0.40)


def viés_favorito_azarao(calibragem: Calibragem) -> dict[str, float | int | None]:
    """O desvio mais documentado em mercado de aposta: o azarão sai caro.

    A literatura de pista de corrida acha isso desde os anos 1940 — apostador
    paga demais por probabilidade baixa e de menos por probabilidade alta. Se o
    Polymarket tiver o mesmo formato, a ponta de baixo mostra erro NEGATIVO (o
    mercado pediu mais do que o mundo entregou) e a de cima, POSITIVO.

    Devolve `None` em cada ponta que não tiver n para afirmar. Este número é o
    único candidato a vantagem que o projeto tem; anunciá-lo com n = 12 seria
    repetir o erro que o resto do repositório inteiro tenta não cometer.
    """
    def junta(faixas: list[Faixa]) -> tuple[int, float | None]:
        n = sum(f.n for f in faixas)
        if n < N_MINIMO_PARA_AJUSTAR:
            return n, None
        preco = sum(f.preco_medio * f.n for f in faixas) / n
        real = sum(f.frequencia_real * f.n for f in faixas) / n
        return n, real - preco

    n_azarao, erro_azarao = junta(calibragem.faixas[:2])   # preço abaixo de 0,20
    n_favorito, erro_favorito = junta(calibragem.faixas[-2:])  # preço acima de 0,80
    return {
        "n_azarao": n_azarao,
        "erro_azarao": erro_azarao,
        "n_favorito": n_favorito,
        "erro_favorito": erro_favorito,
    }
