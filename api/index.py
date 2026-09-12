"""A aplicação web. Entrada da Vercel e do `uvicorn` local.

    uvicorn api.index:app --reload

A Vercel procura um `app` ASGI ou WSGI dentro de `api/`, e o `vercel.json`
reescreve toda rota para cá. Não há build de front-end, não há Node, não há
pacote npm: uma função Python serve HTML pronto.

**A página não calcula nada caro.** Ela lê `data/*.json` e desenha. Todo o custo
— duas mil requisições ao Polymarket, quatro séries do FRED — está no GitHub
Actions, que não tem teto de dez segundos nem cobra por invocação. Se algum dia
uma rota aqui precisar sair para a rede, ela é a rota errada.

**E toda página carimba a idade do que mostra.** Ver `oraculo/guardado.py`: o
dado nasce velho por construção e a idade na tela é o que separa informação de
informação errada.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from oraculo import guardado, visual  # noqa: E402

app = FastAPI(title="Oráculo", docs_url=None, redoc_url=None)
paginas = Jinja2Templates(directory=str(RAIZ / "templates"))


def _decimal(texto: str) -> str:
    """Ponto vira vírgula. **Só no número, e por isso esta função existe.**

    Aplicar `.replace(".", ",")` na string inteira já publicou "+54,7 p,p," na
    tela: o literal "p.p." tem dois pontos e virou dois erros de digitação. A
    troca tem de acontecer ANTES de a unidade ser grudada, nunca depois.
    """
    return texto.replace(".", ",")


def _porcento(valor: float | None, casas: int = 1) -> str:
    """`None` vira travessão, nunca 0%. É a regra do projeto inteira em uma linha."""
    if valor is None or valor != valor:
        return "—"
    return _decimal(f"{valor * 100:.{casas}f}") + "%"


def _numero(valor: float | None, casas: int = 4) -> str:
    if valor is None or valor != valor:
        return "—"
    return _decimal(f"{valor:.{casas}f}")


def _com_sinal(valor: float | None, casas: int = 1) -> str:
    if valor is None or valor != valor:
        return "—"
    return _decimal(f"{valor * 100:+.{casas}f}") + " p.p."


def _sinalizado(valor: float | None, casas: int = 2) -> str:
    """Número puro com sinal explícito. Para o `z`, que não é porcentagem.

    `com_sinal` multiplica por 100 e cola "p.p." — usá-lo num escore-z diria
    "z = +279 p.p.", que é três erros de uma vez.
    """
    if valor is None or valor != valor:
        return "—"
    return _decimal(f"{valor:+.{casas}f}")


def _quando(iso: str | None) -> str:
    """`2026-09-11T23:59:06+00:00` vira `11/09/2026 23:59 UTC`."""
    if not iso:
        return "—"
    try:
        momento = datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    return momento.strftime("%d/%m/%Y %H:%M UTC")


def _idade(bloco: dict | None) -> str:
    minutos = guardado.idade_em_minutos(bloco)
    if minutos is None:
        return "nunca gerado"
    if minutos < 90:
        return f"há {minutos:.0f} min"
    if minutos < 48 * 60:
        return f"há {minutos / 60:.0f} h"
    return f"há {minutos / 1440:.0f} dias"


paginas.env.filters["porcento"] = _porcento
paginas.env.filters["numero"] = _numero
paginas.env.filters["com_sinal"] = _com_sinal
paginas.env.filters["sinalizado"] = _sinalizado
paginas.env.filters["quando"] = _quando


@app.get("/", response_class=HTMLResponse)
def painel(request: Request) -> HTMLResponse:
    bloco = guardado.ler("painel")
    calibragem = guardado.ler("calibragem")
    linhas = (bloco or {}).get("linhas") or []

    for linha in linhas:
        linha["haltere"] = visual.haltere(linha["preco"], linha.get("taxa_base"))

    return paginas.TemplateResponse(
        request=request,
        name="painel.html",
        context={
            "linhas": linhas,
            "sem_familia": (bloco or {}).get("sem_familia") or [],
            "bloco": bloco,
            "idade": _idade(bloco),
            "gerado_em": (bloco or {}).get("gerado_em"),
            "horizonte": (bloco or {}).get("horizonte_da_calibragem"),
            "tem_calibragem": bool(calibragem),
            "aba": "painel",
        },
    )


@app.get("/calibragem", response_class=HTMLResponse)
def calibragem(request: Request) -> HTMLResponse:
    bloco = guardado.ler("calibragem")
    horizontes = (bloco or {}).get("horizontes") or {}

    desenhados = {}
    for chave in sorted(horizontes, key=lambda k: int(k)):
        dados = horizontes[chave]
        desenhados[chave] = {
            **dados,
            "diagrama": visual.diagrama_de_confiabilidade(dados.get("faixas") or []),
        }

    return paginas.TemplateResponse(
        request=request,
        name="calibragem.html",
        context={
            "bloco": bloco,
            "horizontes": desenhados,
            "idade": _idade(bloco),
            "gerado_em": (bloco or {}).get("gerado_em"),
            "aba": "calibragem",
        },
    )


@app.get("/dados/{nome}")
def dados(nome: str) -> JSONResponse:
    """O JSON cru por trás de cada tela.

    Existe para que qualquer número da página possa ser conferido sem clonar o
    repositório. A lista de nomes é fechada: `nome` vem da URL e chega a um
    caminho de arquivo, e sem a lista `../../etc/passwd` também é um nome.
    """
    if nome not in ("painel", "calibragem"):
        return JSONResponse({"erro": "só existem 'painel' e 'calibragem'"}, status_code=404)
    bloco = guardado.ler(nome)
    if bloco is None:
        return JSONResponse({"erro": f"{nome} ainda não foi gerado"}, status_code=404)
    return JSONResponse(bloco)


@app.get("/_sonda")
def sonda(request: Request) -> JSONResponse:
    """O caminho que a plataforma entregou a esta função.

    Ficou permanente porque foi o que resolveu o primeiro deploy, e a resposta
    não era adivinhável: com `rewrites` moderno, **`/` e `/calibragem` chegavam
    os DOIS como `/api/index`**, sem nenhum cabeçalho carregando o caminho
    original. Não é prefixo a remover — é informação destruída, e nenhum
    middleware a recupera.

    Quatro páginas 404 e um JSON `{"detail":"Not Found"}` do FastAPI não dizem
    isso. Esta rota diz, em um deploy, e continua dizendo se a plataforma mudar
    de comportamento. É barata: não lê arquivo, não sai para a rede e não expõe
    nada além do que o próprio requisitante mandou.
    """
    return JSONResponse(
        {
            "scope_path": request.scope.get("path"),
            "root_path": request.scope.get("root_path"),
            "url": str(request.url),
            # `request.app` e não `app`: o nome `app` no fim deste arquivo é
            # reaproveitado pelo envelope, que não tem `.routes`. O Starlette
            # guarda a instância do FastAPI no próprio scope da requisição.
            "rotas": sorted(
                rota.path for rota in request.app.routes if getattr(rota, "path", None)
            ),
        }
    )


class NormalizarCaminho:
    """Tira o prefixo `/api/index` do caminho, quando a plataforma o acrescenta.

    A configuração em `vercel.json` usa `builds` + `routes` com `dest` apontando
    para o ARQUIVO, que preserva o caminho original — e aí este envelope não faz
    nada. Ele existe para o caso do meio: se a plataforma entregar
    `/api/index/calibragem` em vez de `/calibragem`, a rota continua achando a
    página em vez de devolver 404.

    O que ele NÃO conserta, e é importante não se enganar: quando o caminho
    chega colapsado em `/api/index` para toda requisição, a informação de qual
    página foi pedida já não existe. Nesse caso o `/` responde e o resto dá 404,
    e a correção é no `vercel.json`, não aqui.
    """

    def __init__(self, aplicacao, prefixo: str = "/api/index") -> None:
        self.aplicacao = aplicacao
        self.prefixo = prefixo

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            caminho = scope.get("path", "")
            if caminho == self.prefixo or caminho.startswith(self.prefixo + "/"):
                limpo = caminho[len(self.prefixo) :] or "/"
                scope = {**scope, "path": limpo, "raw_path": limpo.encode()}
        await self.aplicacao(scope, receive, send)


# A Vercel e o `uvicorn` procuram um ASGI chamado `app`. O nome passa a apontar
# para o envelope DEPOIS de todas as rotas terem sido registradas — os
# decoradores acima já rodaram contra a instância do FastAPI, que o envelope
# guarda e chama.
app = NormalizarCaminho(app)
