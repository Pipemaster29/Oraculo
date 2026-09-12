"""Onde `data/` mora e como se lê de lá.

Tudo o que o Oráculo sabe vive em arquivos JSON versionados no repositório. Não
há banco, não há `.env`, não há chave. Os scripts gravam, o GitHub Actions
commita, a Vercel republica, a página lê do disco do deploy.

**Todo arquivo carrega a hora em que foi gerado, e a página mostra essa hora.**
A regra é essa e não tem exceção: um painel que mostra um número sem dizer de
quando ele é está afirmando que o número é de agora. Aqui o dado nasce velho por
construção — o Actions roda de hora em hora, a Vercel republica depois — e o
mercado pode ter andado no meio. A idade na tela é o que separa "informação" de
"informação errada".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "data"


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def gravar(nome: str, conteudo: dict[str, Any]) -> Path:
    """Grava `data/<nome>.json` carimbado com a hora."""
    DADOS.mkdir(parents=True, exist_ok=True)
    caminho = DADOS / f"{nome}.json"
    envelope = {"gerado_em": agora_iso(), **conteudo}
    caminho.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return caminho


def ler(nome: str) -> dict[str, Any] | None:
    """Lê `data/<nome>.json`. `None` quando o arquivo não existe ou está corrompido.

    `None` e não `{}`: a página precisa conseguir dizer "este bloco nunca foi
    gerado" em vez de desenhar uma tabela vazia, que se parece com "medi e não
    achei nada".
    """
    caminho = DADOS / f"{nome}.json"
    if not caminho.exists():
        return None
    try:
        valor = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return valor if isinstance(valor, dict) else None


def idade_em_minutos(bloco: dict[str, Any] | None) -> float | None:
    if not bloco or not bloco.get("gerado_em"):
        return None
    try:
        nascimento = datetime.fromisoformat(str(bloco["gerado_em"]))
    except ValueError:
        return None
    if nascimento.tzinfo is None:
        nascimento = nascimento.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - nascimento).total_seconds() / 60.0
