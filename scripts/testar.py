"""Casos-limite das funções puras. Sem rede, sem arquivo, sem servidor.

    python -m scripts.testar

Sai com código diferente de zero quando algum caso falha, então serve de portão
no Actions e antes de commitar.

**Todo caso aqui é um defeito que aconteceu de verdade**, quase todos no dia em
que o projeto foi escrito. Um teste que nunca pegou nada é decoração; os de
baixo têm a data e a consequência anotadas. Quando um novo defeito aparecer,
acrescente o caso ANTES do conserto — é a única forma de saber que o caso pega.
"""

from __future__ import annotations

import math
import sys

from oraculo import calibragem, catalogo, numero, painel, precos, visual
from oraculo.fontes import polymarket

_falhas: list[str] = []


def conferir(condicao: bool, descricao: str) -> None:
    marca = "ok  " if condicao else "FALHA"
    print(f"  {marca} {descricao}")
    if not condicao:
        _falhas.append(descricao)


# ---------------------------------------------------------------------------
print("\nPolymarket: o formato da resposta")
# ---------------------------------------------------------------------------

# A Gamma manda listas como STRING de JSON. Tratar a string como lista funciona
# por acidente — string é iterável — e devolve caractere por caractere, então
# `precos[0]` vira "[" e `float("[")` explode ou, pior, não explode.
conferir(
    polymarket._lista_json('["Yes", "No"]') == ["Yes", "No"],
    "lista vinda como string de JSON é decodificada",
)
conferir(polymarket._lista_json(None) == [], "campo ausente vira lista vazia")
conferir(polymarket._lista_json("nada disso") == [], "string inválida vira lista vazia")

# 11/09/2026: a paginação parava quando a página vinha MENOR que o pedido. Como
# a Gamma devolve no máximo 100 e o código pedia 500, ela parava SEMPRE na
# primeira volta — "pedi 2.500" virava "medi 100", e a calibragem saía sobre
# 1/25 da amostra com todos os números com cara de certos.
conferir(
    polymarket.POR_PAGINA == 100,
    "o tamanho de página é o teto REAL da Gamma (100), não o pedido",
)
conferir(
    polymarket.TETO_DE_OFFSET == 2100,
    "o teto de offset da Gamma está registrado (offset + limit <= 2100)",
)

# ---------------------------------------------------------------------------
print("\nPolymarket: o desfecho de um mercado resolvido")
# ---------------------------------------------------------------------------

def mercado(precos: str, fechado: bool = True, uma: str = "resolved") -> dict:
    return {"closed": fechado, "outcomePrices": precos, "umaResolutionStatus": uma}


conferir(polymarket.desfecho(mercado('["1", "0"]')) == 1, "sim resolvido devolve 1")
conferir(polymarket.desfecho(mercado('["0", "1"]')) == 0, "não resolvido devolve 0")

# Mercado invalidado paga 0,5 para os dois lados. Arredondar para qualquer lado
# inventaria um acerto ou um erro que não houve, e a calibragem é a média
# desses acertos.
conferir(
    polymarket.desfecho(mercado('["0.5", "0.5"]')) is None,
    "mercado invalidado (0,5/0,5) sai da amostra, não vira 0 nem 1",
)
conferir(
    polymarket.desfecho(mercado('["1", "0"]', fechado=False)) is None,
    "mercado ainda aberto não tem desfecho",
)
conferir(
    polymarket.desfecho(mercado('["1", "0"]', uma="disputed")) is None,
    "resolução em disputa sai da amostra",
)

# ---------------------------------------------------------------------------
print("\nPolymarket: preço num horizonte")
# ---------------------------------------------------------------------------

serie = [(1000, 0.2), (2000, 0.3), (3000, 0.4)]
conferir(polymarket.preco_antes(serie, 2500) == 0.3, "pega o último ponto até o limite")
conferir(polymarket.preco_antes(serie, 2000) == 0.3, "o ponto exatamente no limite conta")

# Um mercado que só abriu na véspera não tem preço de sete dias antes. Devolver
# o primeiro ponto que existe usaria um preço de OUTRO horizonte e o chamaria do
# mesmo — e a calibragem de 7 dias ficaria contaminada por preços de 1 dia, que
# acertam muito mais.
conferir(
    polymarket.preco_antes(serie, 500) is None,
    "série que começa depois do limite devolve None, não o primeiro ponto",
)

# ---------------------------------------------------------------------------
print("\nCalibragem: a conta")
# ---------------------------------------------------------------------------

# Mercado perfeito: dez a 0,0 que não aconteceram, dez a 1,0 que aconteceram.
perfeita = [(0.0, 0)] * 10 + [(1.0, 1)] * 10
medida = calibragem.medir(perfeita, horizonte_dias=7)
conferir(medida is not None and abs(medida.brier) < 1e-9, "previsão perfeita tem Brier 0")
conferir(medida is not None and medida.n == 20, "n conta a amostra inteira")

# Amostra vazia não é calibragem perfeita nem péssima: é ausência de medição, e
# tem de viajar como None até a tela.
conferir(calibragem.medir([], horizonte_dias=7) is None, "amostra vazia devolve None")

# `NaN <= 0` e `NaN >= 0` são AMBOS falsos. Um guard escrito como
# `if preco < 0: continue` deixa NaN passar, e daí o Brier inteiro vira NaN.
com_lixo = [(float("nan"), 1), (0.5, 1), (0.5, 0)]
medida_lixo = calibragem.medir(com_lixo, horizonte_dias=7)
conferir(
    medida_lixo is not None and medida_lixo.n == 2,
    "NaN é descartado da amostra (Number.isFinite, não `< 0`)",
)
conferir(
    medida_lixo is not None and not math.isnan(medida_lixo.brier),
    "um NaN na entrada não contamina o Brier",
)

fora_de_faixa = calibragem.medir([(1.5, 1), (0.5, 0)], horizonte_dias=7)
conferir(
    fora_de_faixa is not None and fora_de_faixa.n == 1,
    "preço fora de [0,1] não é preço de contrato binário e sai",
)

# ---------------------------------------------------------------------------
print("\nCalibragem: o ajuste só existe onde há amostra")
# ---------------------------------------------------------------------------

rala = calibragem.medir([(0.35, 1)] * 5, horizonte_dias=7)
conferir(
    rala is not None and rala.ajustar(0.35) is None,
    "faixa com n abaixo do mínimo devolve None, não o preço de volta",
)
farta = calibragem.medir([(0.35, 1)] * 40 + [(0.35, 0)] * 40, horizonte_dias=7)
conferir(farta is not None and farta.ajustar(0.35) is not None, "faixa farta ajusta")
conferir(farta is not None and farta.ajustar(1.7) is None, "preço impossível não ajusta")

# ---------------------------------------------------------------------------
print("\nCalibragem: a banda")
# ---------------------------------------------------------------------------

sem_desvio = calibragem.medir([(0.25, 1)] * 25 + [(0.25, 0)] * 75, horizonte_dias=7)
resultado = calibragem.banda(sem_desvio, 0.2, 0.3)
conferir(
    resultado["z"] is not None and abs(resultado["z"]) < 0.5,
    "preço que bate com a frequência dá z perto de zero",
)
minuscula = calibragem.medir([(0.25, 1)] * 3, horizonte_dias=7)
conferir(
    calibragem.banda(minuscula, 0.2, 0.3)["z"] is None,
    "banda sem n devolve z None, não um z calculado sobre três observações",
)

# ---------------------------------------------------------------------------
print("\nPainel: o que tem cara de economia")
# ---------------------------------------------------------------------------

# 11/09/2026: o filtro testava `chave in pergunta.lower()`, e a lista de órfãos
# veio com "Russian FEDeration" (por `fed`) e "PhiliPPInes" (por `ppi`). Sigla
# de três letras cabe dentro de meio dicionário.
conferir(
    not painel._parece_economia("Communist Party of the Russian Federation wins?"),
    "'Federation' não é economia (o `fed` está no meio da palavra)",
)
conferir(
    not painel._parece_economia("China x Philippines military clash before 2027?"),
    "'Philippines' não é economia (o `ppi` está no meio da palavra)",
)
conferir(painel._parece_economia("Fed rate hike in 2026?"), "'Fed' solto é economia")
conferir(painel._parece_economia("Will CPI come in hot?"), "'CPI' solto é economia")

# ---------------------------------------------------------------------------
print("\nVisual: geometria")
# ---------------------------------------------------------------------------

# Faixa sem observação desenhada no centro do balde com frequência zero coloca
# um ponto colado no eixo x, que o olho lê como "nunca aconteceu" quando o que
# houve foi "nunca foi perguntado".
faixas = [
    {"piso": 0.0, "teto": 0.1, "n": 0, "preco_medio": 0.05, "frequencia_real": 0.0, "confiavel": False},
    {"piso": 0.4, "teto": 0.5, "n": 50, "preco_medio": 0.45, "frequencia_real": 0.5, "confiavel": True},
]
desenho = visual.diagrama_de_confiabilidade(faixas)
conferir(len(desenho["pontos"]) == 1, "faixa com n=0 não vira ponto no gráfico")

vazio = visual.diagrama_de_confiabilidade([])
conferir(vazio["pontos"] == [] and vazio["linha"] == "", "diagrama sem dado não explode")

# Sem taxa-base não há marca da história. Colocá-la em zero afirmaria "a
# história diz que isto nunca acontece", que é uma leitura, não uma ausência.
conferir(
    visual.haltere(0.8, None)["historia"] is None,
    "haltere sem taxa-base não desenha a marca da história em zero",
)
h = visual.haltere(0.0, 1.0)
conferir(
    h["mercado"] == 0.0 and h["historia"] == visual.REGUA,
    "as pontas da régua ficam nas pontas",
)
conferir(
    visual.haltere(1.4, -0.2)["mercado"] == visual.REGUA,
    "valor fora de [0,1] é preso à régua em vez de desenhar fora do quadro",
)

# ---------------------------------------------------------------------------
print("\nNúmero em convenção brasileira")
# ---------------------------------------------------------------------------

# Os dois defeitos reais que fizeram este módulo existir. Ver o cabeçalho de
# `oraculo/numero.py`: os dois vieram de `.replace` sobre a FRASE em vez de
# sobre o número.
conferir(numero.br(1234567.5) == "1.234.567,50", "ponto no milhar, vírgula no decimal")
conferir(numero.dinheiro(45000) == "US$ 45.000", "quarenta e cinco mil não vira 'US$ 45,000'")
conferir(numero.dinheiro(97.26) == "US$ 97,26", "abaixo de mil, o centavo fica")
conferir(numero.br(None) == "—" and numero.porcento(float("nan")) == "—",
         "ausência vira travessão, nunca zero")
conferir(numero.porcento(0.094, 0, sinal=True) == "+9%", "fração vira porcentagem com sinal")

# ---------------------------------------------------------------------------
print("\nPreço: toque e fechamento são perguntas diferentes")
# ---------------------------------------------------------------------------

# Série sintética: sobe até 120 no meio de cada janela e volta para 100.
# "Tocou 120?" é sim; "terminou acima de 120?" é não. É exatamente o caso que a
# família de toque respondia errado ao pegar "be above $78,000 on September 12"
# pelo "above" — 34,1% de resposta para um mercado precificado a 5,5%.
import datetime  # noqa: E402

base = datetime.date(2000, 1, 1)
dente = []
for ciclo in range(400):
    for passo, valor in enumerate((100.0, 110.0, 120.0, 110.0)):
        dente.append((base + datetime.timedelta(days=ciclo * 4 + passo), valor))

toque = precos.taxa_de_toque(dente, alvo=120.0 * dente[-1][1] / 100.0, horizonte_dias=4)
fecha = precos.taxa_de_fechamento(dente, alvo=120.0 * dente[-1][1] / 100.0, horizonte_dias=4)
conferir(
    toque.valor > fecha.valor,
    f"tocar é sempre mais provável que terminar lá ({toque.valor:.2f} > {fecha.valor:.2f})",
)

# O alvo já do lado certo não é pergunta sobre o futuro. Devolver 100% poria a
# maior discrepância do painel numa pergunta que já venceu.
try:
    precos.taxa_de_toque(dente, alvo=1.0, horizonte_dias=4)
    conferir(False, "alvo já atingido deveria recusar")
except precos.SemAmostra:
    conferir(True, "alvo já do lado certo do preço recusa em vez de devolver 100%")

# Horizonte que não cabe na série: recusa em vez de medir sobre duas janelas.
try:
    precos.taxa_de_toque(dente, alvo=dente[-1][1] * 3, horizonte_dias=100_000)
    conferir(False, "horizonte impossível deveria recusar")
except precos.SemAmostra:
    conferir(True, "horizonte maior que a série recusa")

# ---------------------------------------------------------------------------
print("\nCatálogo: leitura do valor e roteamento da família")
# ---------------------------------------------------------------------------

# A vírgula do Polymarket é separador de MILHAR. Lida como decimal, "$45,000"
# vira quarenta e cinco dólares — e a taxa-base de "o bitcoin cai para US$ 45"
# é zero, um zero que pareceria medição.
conferir(catalogo._para_numero("45,000", None) == 45000.0, "'45,000' é quarenta e cinco mil")
conferir(catalogo._para_numero("150", "k") == 150000.0, "'150k' é cento e cinquenta mil")
conferir(catalogo._para_numero("1.5", "M") == 1_500_000.0, "'1.5M' é um milhão e meio")


def familia_de(pergunta: str) -> str | None:
    for familia in catalogo.FAMILIAS:
        if familia.padrao.search(pergunta):
            return familia.nome
    return None


conferir(
    familia_de("Will the price of Bitcoin be above $78,000 on September 12?")
    == "Preço: acima na data",
    "'be above X on DATE' vai para a família de FECHAMENTO",
)
conferir(
    familia_de("Will Bitcoin hit $150k by December 31, 2026?") == "Preço: toque para cima",
    "'hit X by DATE' vai para a família de TOQUE",
)
conferir(
    familia_de("Will Bitcoin dip to $45,000 by December 31, 2026?")
    == "Preço: toque para baixo",
    "'dip to X' vai para o toque para baixo",
)
conferir(
    familia_de("Will Crude Oil reach a new all-time high by December 31?")
    == "Preço: nova máxima histórica",
    "'new all-time high' casa antes da família de toque genérica",
)
conferir(
    familia_de("Will the U.S. invade Iran before 2027?") is None,
    "guerra não casa com nenhuma família — não há série que responda",
)

# ---------------------------------------------------------------------------
print("\nFormatação da página")
# ---------------------------------------------------------------------------

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from api.index import _com_sinal, _porcento, _sinalizado  # noqa: E402

# 11/09/2026: `f"{x:+.1f} p.p.".replace(".", ",")` publicou "+54,7 p,p," na tela.
# A troca de separador decimal tem de acontecer ANTES de a unidade ser grudada.
conferir(_com_sinal(0.547) == "+54,7 p.p.", "o 'p.p.' sobrevive à vírgula decimal")
conferir(_porcento(0.258) == "25,8%", "porcentagem com vírgula")
conferir(_porcento(None) == "—", "None vira travessão, nunca 0%")
conferir(_porcento(float("nan")) == "—", "NaN vira travessão, nunca 0%")
conferir(_sinalizado(2.79) == "+2,79", "z sai com sinal e sem 'p.p.'")

# ---------------------------------------------------------------------------
print()
if _falhas:
    print(f"{len(_falhas)} caso(s) falharam:")
    for falha in _falhas:
        print(f"  - {falha}")
    raise SystemExit(1)
print("todos os casos passaram")
