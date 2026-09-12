"""De uma pergunta do Polymarket para uma taxa-base no FRED.

**O que uma taxa-base é:** com que frequência isto aconteceu historicamente,
num período comparável ao que a pergunta cobre.

**O que ela NÃO é, e esta é a frase mais importante do arquivo:** uma previsão.
O Fed subiu juros em 48,8% dos anos desde 1983; isso não quer dizer que a chance
de alta em 2026 seja 48,8%, porque 2026 não é um ano sorteado do chapéu — tem
uma inflação medida, um desemprego medido e um comitê que já falou. O mercado
sabe tudo isso e a taxa-base não sabe nada disso.

Então para que serve? Para dar **escala** ao preço. Um mercado a 0,89 para "alta
de juros em 2026" não diz nada sozinho. Ao lado de uma taxa-base de 0,49 ele
passa a dizer uma coisa concreta e verificável: *o mercado acha este ano quase
duas vezes mais propenso a alta do que um ano típico dos últimos quarenta*. Essa
é uma afirmação que se pode discutir, e é tudo o que o Oráculo se propõe a
colocar na tela.

**Casar pergunta com série é feito à mão, uma família de cada vez.** Não há
inferência automática aqui e não deve haver: adivinhar qual série responde qual
pergunta é o tipo de erro que sai barato de escrever e caro de descobrir. O que
não casa com nenhuma família fica **sem taxa-base** — e a página escreve "sem
taxa-base", nunca zero.

Todos os números nos comentários abaixo foram medidos em 11/09/2026 e podem ser
refeitos com `python -m scripts.taxas_base`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Callable

from oraculo.fontes import fred


class SemResolucao(RuntimeError):
    """A família reconhece a pergunta e o método não a responde nesta resolução.

    Terceiro estado, e ele precisa existir separado dos outros dois. "Nenhuma
    família reconheceu" é buraco de catálogo; "o FRED não respondeu" é falha de
    rede; isto aqui é o método sabendo o próprio limite. Os três aparecem
    diferentes na tela porque significam coisas diferentes para quem lê — e o
    pior desfecho possível seria qualquer um deles virar o número 0%.
    """


@dataclass
class TaxaBase:
    valor: float
    n: int
    janela: str
    descricao: str
    ressalva: str
    series: list[str]


@dataclass
class Familia:
    nome: str
    padrao: re.Pattern[str]
    justificativa: str
    calcular: Callable[[re.Match[str]], TaxaBase | None]


# --------------------------------------------------------------------------
# O alvo do Fed, emendado
# --------------------------------------------------------------------------
# Até 2008-12-15 o Fed anunciava um alvo único (`DFEDTAR`); a partir de
# 2008-12-16 anuncia uma FAIXA, e o que continua a série é o topo dela
# (`DFEDTARU`). Usar só a segunda encurta a história para 2008 e joga fora o
# ciclo de alta de 1994, o de 1999 e o de 2004 — três dos cinco ciclos de alta
# que existem. Usar só a primeira para em 2008.
#
# A emenda é pelo DIA: tudo de `DFEDTAR` até o último dia dela, e de `DFEDTARU`
# só o que vem depois. Sem o corte por data as duas se sobrepõem em 2008 e a
# sobreposição inventa eventos de mudança que não houve.
#
# MEDIDO: 1982-09-27 a 2026-09-11, 16.056 dias, 184 eventos de mudança
# (93 altas, 91 cortes).


@lru_cache(maxsize=1)
def _alvo_do_fed() -> list[tuple[date, float]]:
    antigo = [(d, v) for d, v in fred.serie("DFEDTAR") if v is not None]
    novo = [(d, v) for d, v in fred.serie("DFEDTARU") if v is not None]
    if not antigo or not novo:
        raise fred.FalhaDeLeitura("alvo do Fed: uma das duas séries veio vazia")
    emenda = antigo[-1][0]
    return antigo + [(d, v) for d, v in novo if d > emenda]


@lru_cache(maxsize=1)
def _eventos_do_fed() -> list[tuple[date, float]]:
    """`(dia, variação)` a cada mudança do alvo. Só muda em decisão do comitê."""
    alvo = _alvo_do_fed()
    return [
        (dia, atual - anterior)
        for (_, anterior), (dia, atual) in zip(alvo, alvo[1:])
        if abs(atual - anterior) > 1e-9
    ]


# O FOMC se reúne oito vezes por ano desde 1981. O número está aqui, sozinho e
# nomeado, porque ele é uma SUPOSIÇÃO e não uma leitura: o FRED serve a taxa,
# não o calendário do comitê. Toda taxa-base por reunião herda essa suposição, e
# a ressalva de cada uma diz isso na tela.
REUNIOES_POR_ANO = 8


def _por_reuniao(quantos: int, descricao: str) -> TaxaBase:
    """`quantos` é a contagem de reuniões, já feita pelo chamador.

    Recebe o número pronto em vez de um filtro sobre eventos porque uma das três
    famílias — "sem mudança" — não é uma contagem de eventos, é o COMPLEMENTO
    delas. Na versão anterior ela passava um filtro que nunca casava, contava
    zero evento e publicava taxa-base 0,0% para o desfecho mais comum do
    conjunto (que é 48,9%). Com o filtro na assinatura esse erro é natural de
    escrever; com o número, não.
    """
    alvo = _alvo_do_fed()
    anos = alvo[-1][0].year - alvo[0][0].year + 1
    reunioes = REUNIOES_POR_ANO * anos
    return TaxaBase(
        valor=quantos / reunioes,
        n=reunioes,
        janela=f"{alvo[0][0].year}–{alvo[-1][0].year}",
        descricao=descricao,
        ressalva=(
            f"Supõe {REUNIOES_POR_ANO} reuniões por ano — o FRED serve a taxa, não o "
            "calendário do comitê. E trata todas as reuniões como iguais, quando na "
            "prática elas vêm em ciclos: depois de uma alta, a alta seguinte é muito "
            "mais provável que esta média sugere."
        ),
        series=["DFEDTAR", "DFEDTARU"],
    )


def _reunioes_com(filtro: Callable[[float], bool], descricao: str) -> TaxaBase:
    quantos = sum(1 for _, delta in _eventos_do_fed() if filtro(delta))
    return _por_reuniao(quantos, descricao)


def _reunioes_sem_mudanca() -> TaxaBase:
    """MEDIDO: 184 eventos em 360 reuniões supostas → 48,9% sem mudança.

    É o desfecho mais comum, e por larga margem. Um painel que mostrasse zero
    aqui estaria errado justamente no número que mais aparece.
    """
    alvo = _alvo_do_fed()
    anos = alvo[-1][0].year - alvo[0][0].year + 1
    reunioes = REUNIOES_POR_ANO * anos
    return _por_reuniao(reunioes - len(_eventos_do_fed()), "reuniões sem mudança no alvo")


def _cortes_e_altas_por_ano() -> dict[int, tuple[int, int]]:
    """`{ano: (nº de altas, nº de cortes)}`, só de anos COMPLETOS."""
    alvo = _alvo_do_fed()
    contagem: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for dia, delta in _eventos_do_fed():
        contagem[dia.year][0 if delta > 0 else 1] += 1
    # O primeiro ano começa em setembro e o último ainda não acabou: nenhum dos
    # dois é um ano de doze meses, e contar qualquer um dos dois como "ano sem
    # alta" seria contar um ano que não existiu.
    primeiro, ultimo = alvo[0][0].year, alvo[-1][0].year
    return {
        ano: (contagem[ano][0], contagem[ano][1])
        for ano in range(primeiro + 1, ultimo)
    }


def _por_ano(filtro: Callable[[int, int], bool], descricao: str) -> TaxaBase:
    anos = _cortes_e_altas_por_ano()
    quantos = sum(1 for altas, cortes in anos.values() if filtro(altas, cortes))
    chaves = sorted(anos)
    return TaxaBase(
        valor=quantos / len(anos),
        n=len(anos),
        janela=f"{chaves[0]}–{chaves[-1]}, anos completos",
        descricao=descricao,
        ressalva=(
            "Frequência sobre anos civis inteiros. Um mercado aberto em setembro "
            "pergunta sobre os meses que SOBRAM do ano, que são menos — a taxa-base "
            "de ano cheio é, para ele, generosa."
        ),
        series=["DFEDTAR", "DFEDTARU"],
    )


# --------------------------------------------------------------------------
# O NÍVEL do alvo no fim do ano
# --------------------------------------------------------------------------
# "A taxa vai estar em 4,0% no fim de 2026?" é uma pergunta de natureza
# diferente das de cima. Frequência histórica pura não responde: o alvo já
# esteve em 19% e já esteve em 0,25%, e contar em que fração dos anos ele
# terminou perto de 4% mede a história do NÍVEL, que não tem nada a ver com
# 2026 — o alvo hoje é o que é, e o ano que vem começa de lá.
#
# O que responde: **de onde estamos, para onde o Fed costuma ir em doze meses.**
# Pego a variação de dezembro a dezembro de cada ano histórico, aplico cada uma
# delas ao alvo de HOJE, e conto em que fração das trajetórias o resultado
# satisfaz a pergunta. É uma reamostragem das variações anuais observadas.
#
# A suposição — e ela é forte — é que a distribuição de variações anuais não
# depende do nível de partida. É falsa nas pontas: de 0,25% não dá para cair
# 3 pontos, e o histórico tem quedas de 5. A ressalva diz isso na tela, e o
# efeito é sempre o mesmo: alarga demais a cauda de baixo quando o alvo está
# baixo.


@lru_cache(maxsize=1)
def _variacoes_anuais_do_alvo() -> list[float]:
    """Variação do alvo de fim de ano a fim de ano, em pontos percentuais."""
    alvo = _alvo_do_fed()
    fim_do_ano: dict[int, float] = {}
    for dia, valor in alvo:
        fim_do_ano[dia.year] = valor  # a série é diária e ordenada: o último vence
    anos = sorted(fim_do_ano)
    # O último ano ainda não terminou, então o "fim" dele é hoje e a variação
    # seria de um ano parcial contada como ano inteiro.
    return [fim_do_ano[b] - fim_do_ano[a] for a, b in zip(anos, anos[1:-1])]


def _nivel_no_fim_do_ano(limiar: float, ao_menos: bool) -> TaxaBase:
    variacoes = _variacoes_anuais_do_alvo()
    hoje = _alvo_do_fed()[-1][1]
    # O Fed move em múltiplos de 25 pontos-base, então a trajetória também
    # aterrissa neles. Sem o arredondamento, "exatamente 4,0%" quase nunca casa
    # e a taxa-base sai zero por artefato de aritmética, não por medição.
    destinos = [round((hoje + variacao) * 4) / 4 for variacao in variacoes]
    destinos = [max(0.0, d) for d in destinos]  # o alvo não foi negativo nos EUA

    if not ao_menos:
        # MEDIDO em 11/09/2026, com o alvo em 3,75%: das 43 variações anuais,
        # NENHUMA é +0,50. Então "exatamente 4,25%" dá zero trajetória — e 4,00%
        # e 4,50%, os vizinhos de 25 pontos-base, dão três cada.
        #
        # Esse zero é verdadeiro sobre a amostra e falso sobre o mundo: é buraco
        # de histograma de 43 pontos numa grade de 25 pontos-base, não
        # impossibilidade. Publicá-lo ao lado de um mercado a 30% seria dizer "a
        # história diz que nunca acontece" quando o que a história diz é "não
        # tenho amostra nessa resolução".
        #
        # Então esta variante se RECUSA. A acumulada ("X% ou mais") continua,
        # porque somar a cauda inteira passa por cima dos buracos. Para responder
        # a exata seria preciso outro método — densidade suavizada, ou variação
        # em pontos-base em vez de anos civis — e enquanto ele não existir a
        # resposta certa é não ter resposta.
        raise SemResolucao(
            f"nível exato ({limiar:g}%) não é respondível com {len(destinos)} variações "
            "anuais numa grade de 25 pontos-base: a amostra tem buracos, e um buraco "
            "viraria '0%' na tela. A variante 'X% ou mais' é medida"
        )

    quantos = sum(1 for d in destinos if d >= limiar - 1e-9)
    descricao = f"trajetórias que terminam em {limiar:g}% ou mais"

    return TaxaBase(
        valor=quantos / len(destinos),
        n=len(destinos),
        janela=f"{len(destinos)} variações anuais do alvo, a partir de {hoje:g}% hoje",
        descricao=descricao,
        ressalva=(
            f"Não é frequência histórica do nível: é o alvo de hoje ({hoje:g}%) mais "
            "cada variação de doze meses já observada. Duas suposições, as duas "
            "fortes. (1) A distribuição das variações não depende de onde se parte, "
            "o que é falso perto de zero: de um alvo baixo não cabe uma queda de 5 "
            "pontos, e o histórico tem. (2) O horizonte é de doze meses, mas um "
            "mercado de 'fim de 2026' aberto em setembro pergunta sobre três meses "
            "e meio. Nos dois casos o erro vai para o mesmo lado — a distribuição "
            "sai LARGA demais, então a taxa-base exagera a chance dos níveis longe "
            "do atual."
        ),
        series=["DFEDTAR", "DFEDTARU"],
    )


# --------------------------------------------------------------------------
# Inflação e recessão
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _cpi_anual() -> dict[int, float]:
    """`{ano: maior variação de 12 meses vista naquele ano, em %}`.

    Doze meses e não um mês: "inflação chegou a 5%" no uso corrente é a variação
    acumulada em doze meses, que é o número que sai na manchete. O mês contra o
    mês anterior é dez vezes menor e compará-lo com o limiar da pergunta
    responderia outra coisa.
    """
    cpi = [(d, v) for d, v in fred.serie("CPIAUCSL") if v is not None]
    pico: dict[int, float] = {}
    for (_, antes), (dia, agora) in zip(cpi, cpi[12:]):
        if antes <= 0:
            continue
        anual = (agora / antes - 1.0) * 100.0
        pico[dia.year] = max(pico.get(dia.year, float("-inf")), anual)
    return pico


def _inflacao_acima(limiar: float) -> TaxaBase:
    # MEDIDO: >3% em 66,7% dos anos, >4% em 41,0%, >5% em 29,5%, >6% em 21,8%.
    pico = _cpi_anual()
    ultimo = max(pico)
    completos = {ano: v for ano, v in pico.items() if ano < ultimo}
    quantos = sum(1 for v in completos.values() if v > limiar)
    return TaxaBase(
        valor=quantos / len(completos),
        n=len(completos),
        janela=f"{min(completos)}–{max(completos)}",
        descricao=f"anos em que a inflação de 12 meses passou de {limiar:g}% em algum mês",
        ressalva=(
            "A janela inclui os anos 70. Contando só de 1990 para cá, a frequência "
            "cai muito — a economia que produziu esses números tinha outro regime "
            "monetário, e a média de setenta anos mistura os dois."
        ),
        series=["CPIAUCSL"],
    )


@lru_cache(maxsize=1)
def _recessao_por_ano() -> dict[int, int]:
    """`{ano: meses em recessão segundo o NBER}`."""
    meses: dict[int, int] = defaultdict(int)
    for dia, valor in fred.serie("USREC"):
        if valor is not None:
            meses[dia.year] += int(valor)
    return dict(meses)


# A janela começa em 1948 e não em 1854, e a escolha muda MUITO o número:
# 45,3% dos anos desde 1854 têm recessão, contra 26,9% desde 1948. A economia
# pré-guerra tinha recessão quase uma vez a cada dois anos, sem banco central
# moderno e sem estabilizador automático. Herdar aquela frequência para 2026
# seria usar um mundo diferente como referência. A ressalva na tela cita as
# duas.
PRIMEIRO_ANO_DE_RECESSAO = 1948


def _recessao_no_ano() -> TaxaBase:
    por_ano = _recessao_por_ano()
    ultimo = max(por_ano)
    completos = {a: m for a, m in por_ano.items() if PRIMEIRO_ANO_DE_RECESSAO <= a < ultimo}
    quantos = sum(1 for meses in completos.values() if meses > 0)
    return TaxaBase(
        valor=quantos / len(completos),
        n=len(completos),
        janela=f"{min(completos)}–{max(completos)}",
        descricao="anos com ao menos um mês de recessão pelo NBER",
        ressalva=(
            "Desde 1854 a frequência seria 45,3% em vez desta — a escolha da janela "
            "quase dobra o número. E o NBER data recessão com meses de atraso: um "
            "mercado que resolve em dezembro pode não ter o veredito a tempo."
        ),
        series=["USREC"],
    )


# --------------------------------------------------------------------------
# As famílias
# --------------------------------------------------------------------------
# Cada padrão foi escrito contra perguntas que estavam ABERTAS no Polymarket em
# 11/09/2026, copiadas da Gamma e não imaginadas. Quando um formato novo
# aparecer, o jeito de descobrir é `python -m scripts.taxas_base --sem-familia`,
# que lista os mercados econômicos que nenhuma família pegou.

FAMILIAS: list[Familia] = [
    Familia(
        nome="Fed: alta na reunião",
        padrao=re.compile(r"fed increase interest rates by .* after the .* meeting", re.I),
        justificativa=(
            "O alvo do Fed é uma série diária no FRED e só se mexe em decisão do "
            "comitê. Contar os dias em que ela subiu conta exatamente as altas."
        ),
        calcular=lambda _: _reunioes_com(lambda d: d > 0, "reuniões que terminaram em alta"),
    ),
    Familia(
        nome="Fed: corte na reunião",
        padrao=re.compile(r"fed decrease interest rates by .* after the .* meeting", re.I),
        justificativa="O espelho da anterior, nos dias em que a série caiu.",
        calcular=lambda _: _reunioes_com(lambda d: d < 0, "reuniões que terminaram em corte"),
    ),
    Familia(
        nome="Fed: sem mudança na reunião",
        padrao=re.compile(r"no change in fed interest rates after the .* meeting", re.I),
        justificativa=(
            "O complemento dos dois de cima: reuniões sem nenhum evento de mudança. "
            "Vale conferir que os três somam 1 — se não somarem, uma das contas "
            "está contando duas vezes."
        ),
        calcular=lambda _: _reunioes_sem_mudanca(),
    ),
    Familia(
        nome="Fed: alguma alta no ano",
        padrao=re.compile(r"fed rate hike in (20\d\d)", re.I),
        justificativa="Anos civis completos com ao menos um evento de alta.",
        calcular=lambda _: _por_ano(
            lambda altas, _cortes: altas > 0, "anos com ao menos uma alta do alvo"
        ),
    ),
    Familia(
        nome="Fed: nenhum corte no ano",
        padrao=re.compile(r"no fed rate cuts? happen in (20\d\d)", re.I),
        justificativa="Anos civis completos em que o alvo não caiu nenhuma vez.",
        calcular=lambda _: _por_ano(
            lambda _altas, cortes: cortes == 0, "anos sem nenhum corte do alvo"
        ),
    ),
    Familia(
        nome="Fed: exatamente N cortes no ano",
        padrao=re.compile(r"will (\d+) fed rate cuts? happen in (20\d\d)", re.I),
        justificativa=(
            "A distribuição medida do número de cortes por ano é muito torta: "
            "21 anos com zero, e a cauda chegando a 11 em 2008. A frequência de um "
            "N específico é pequena para quase todo N, e é isso que a taxa-base diz."
        ),
        calcular=lambda achado: _por_ano(
            lambda _altas, cortes, alvo=int(achado.group(1)): cortes == alvo,
            f"anos com exatamente {achado.group(1)} corte(s) do alvo",
        ),
    ),
    Familia(
        nome="Fed: N cortes ou mais no ano",
        padrao=re.compile(r"will (\d+) or more fed rate cuts? happen in (20\d\d)", re.I),
        justificativa=(
            "O acumulado da família anterior. Separada porque 'ou mais' junta a "
            "cauda inteira, e a cauda é onde está quase toda a massa: 2008 teve 11 "
            "cortes sozinho."
        ),
        calcular=lambda achado: _por_ano(
            lambda _altas, cortes, alvo=int(achado.group(1)): cortes >= alvo,
            f"anos com {achado.group(1)} corte(s) ou mais do alvo",
        ),
    ),
    Familia(
        nome="Fed: nível do alvo no fim do ano",
        padrao=re.compile(
            r"upper bound of the target federal funds rate be\s*"
            r"(≥|>=|at least)?\s*([\d.]+)\s*%\s*at the end of",
            re.I,
        ),
        justificativa=(
            "Reamostragem das variações anuais do alvo a partir do nível de hoje. "
            "Ver o bloco 'O NÍVEL do alvo no fim do ano' — frequência histórica do "
            "nível responderia outra pergunta."
        ),
        calcular=lambda achado: _nivel_no_fim_do_ano(
            float(achado.group(2)), ao_menos=bool(achado.group(1))
        ),
    ),
    Familia(
        nome="Inflação acima de um limiar no ano",
        padrao=re.compile(r"inflation reach (?:more than|above|over) ([\d.]+)\s*%", re.I),
        justificativa=(
            "CPI cheio, variação de 12 meses, pico do ano contra o limiar da "
            "pergunta. É a definição que a manchete usa."
        ),
        calcular=lambda achado: _inflacao_acima(float(achado.group(1))),
    ),
    Familia(
        nome="Recessão nos EUA no ano",
        padrao=re.compile(r"\brecession\b.*\b(20\d\d)\b|\brecession by end of\b", re.I),
        justificativa=(
            "`USREC` é o indicador oficial do NBER, mensal e binário. Um ano "
            "'tem recessão' se qualquer mês dele estiver marcado."
        ),
        calcular=lambda _: _recessao_no_ano(),
    ),
]


def taxa_base_de(pergunta: str) -> tuple[Familia, TaxaBase] | None:
    """A primeira família que casar com a pergunta, e a taxa-base dela.

    `None` quando nenhuma casa — que é o caso da grande maioria dos mercados do
    Polymarket, porque a grande maioria é sobre política, esporte e cultura, e o
    FRED não tem série para "quem ganha a eleição". Isso não é falha: é o
    catálogo se recusando a inventar uma referência.

    Também devolve `None` quando a família casa mas a série do FRED não lê. As
    duas situações são diferentes e o chamador que quiser distingui-las usa
    `explicar`.
    """
    resultado = explicar(pergunta)
    if resultado is None or resultado[1] is None:
        return None
    return resultado[0], resultado[1]


def explicar(pergunta: str) -> tuple[Familia, TaxaBase | None, str] | None:
    """Como `taxa_base_de`, mas separa "não casou" de "casou e não li".

    - `None` — nenhuma família reconhece a pergunta.
    - `(familia, None, motivo)` — reconheci, mas o FRED não respondeu. Isto é
      uma FALHA e tem de aparecer como falha, não como ausência de referência.
    - `(familia, taxa, "")` — medi.
    """
    if not pergunta:
        return None
    for familia in FAMILIAS:
        achado = familia.padrao.search(pergunta)
        if not achado:
            continue
        try:
            return familia, familia.calcular(achado), ""
        except SemResolucao as limite:
            return familia, None, f"sem taxa-base: {limite}"
        except fred.FalhaDeLeitura as erro:
            return familia, None, f"o FRED não respondeu: {erro}"
        except (ValueError, ZeroDivisionError, KeyError) as erro:
            return familia, None, f"a família casou mas a conta não fechou: {erro}"
    return None
