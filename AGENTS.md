# oraculo — o que é, como funciona, como mexer

Compara o que o Polymarket precifica hoje com o que os dados econômicos
registraram, e mede antes de tudo se o preço do mercado merece confiança.

**Tudo vem de fonte pública e sem nenhuma chave de API.** Gamma e CLOB do
Polymarket para os mercados e o histórico de preço; `fredgraph.csv` do FRED para
as séries do Fed, do CPI e do NBER.

A frase "sem nenhuma chave" é restrição de projeto e não descrição. A API oficial
do FRED (`api.stlouisfed.org`) pede cadastro e serve exatamente as mesmas séries
que o gerador de gráfico do próprio site entrega em CSV sem pedir nada.

O `README.md` conta o que foi medido, com os números. Este arquivo é o mapa para
trabalhar no código.

---

## A regra que organiza tudo

**Nada entra sem medição, e o que foi medido e não funciona fica escrito.**

Este projeto começou para achar mercados mal precificados. A primeira medição
disse que eles quase não existem, e o projeto mudou de forma em vez de mudar a
medição. Três exemplos com número, todos visíveis na própria tela:

- **O Polymarket é quase perfeitamente calibrado.** Sobre 1.678 mercados
  resolvidos, sete dias antes do fim, a confiabilidade é **0,0013** — o preço
  fica a três milésimos da frequência observada. Não há o que corrigir.
- **O viés favorito–azarão não aparece.** A literatura de pista de corrida acha
  azarão caro desde os anos 1940. Aqui a ponta de baixo erra +0,017 e a de cima
  +0,018: as duas para o mesmo lado e por nada.
- **O único desvio que separa foi escolhido depois de ver os dados.** A banda
  0,10–0,40 sai +0,080 com z = 2,79, e repete nos três horizontes. Está na tela
  com as duas ressalvas que a derrubam: a janela foi escolhida a posteriori, e o
  z supõe independência que mercados do mesmo evento não têm.

Se você for propor algo novo, meça primeiro. Se não der para medir, escreva que
não deu — e veja `SemResolucao` em `oraculo/catalogo.py`, que é exatamente isso
virando código.

---

## Como rodar

```bash
pip install -r requirements.txt

python -m scripts.calibrar    # mede a calibração → data/calibragem.json  (~10 min)
python -m scripts.montar      # monta o painel    → data/painel.json      (~20 s)
python -m scripts.testar      # casos-limite, sem rede
python -m scripts.auditar     # invariantes do que está em data/

uvicorn api.index:app --reload   # a página em http://127.0.0.1:8000
```

Não há chave, `.env` nem banco. O estado inteiro mora em `data/`.

### Os dois relógios, que são diferentes de propósito

| o quê | com que frequência | por quê |
|---|---|---|
| o painel: preço, taxa-base, ajuste | **de hora em hora** | ~21 requisições. O preço de um mercado macro anda em dias |
| a calibragem sobre mercados resolvidos | **uma vez por dia** | ~2.100 requisições. Um dia a mais numa amostra de dois mil move a terceira casa do Brier |

O `schedule` do GitHub atrasa e descarta sob carga, e aqui isso **não** é
problema: uma execução que atrasa duas horas custa duas horas de preço velho, e
a página carimba a própria idade para que isso seja visível. Se um dia o projeto
cobrir mercado que se move em minutos, a resposta não será cron mais agressivo —
será execução mais longa.

---

## Arquitetura

### A página não calcula nada

`api/index.py` lê `data/*.json` e desenha. Todo o custo está no GitHub Actions,
que não tem teto de dez segundos nem cobra por invocação. **Se alguma rota
precisar sair para a rede, ela é a rota errada.**

Na Vercel o disco da função é o do BUILD, e o build só roda no push. Como o
Actions commita `data/` e o push dispara o deploy, o arquivo do deploy é sempre o
do último commit. **Não acrescente `ignoreCommand` ao `vercel.json`**: pular o
build quando só `data/` mudou congelaria a página para sempre, sem erro e sem
aviso.

### Os módulos

| arquivo | responsabilidade |
|---|---|
| `oraculo/fontes/polymarket.py` | Gamma e CLOB. **Sabe os tetos reais da fonte** e por que cada um está lá |
| `oraculo/fontes/fred.py` | `fredgraph.csv`, sem chave. `"."` vira `None`, nunca `0.0` |
| `oraculo/calibragem.py` | o mercado é calibrado? Brier, decomposição de Murphy, curva de confiabilidade |
| `oraculo/catalogo.py` | de uma pergunta do Polymarket para uma série do FRED. **Uma família por vez, escrita à mão, com justificativa** |
| `oraculo/painel.py` | junta preço + taxa-base + ajuste numa linha por mercado |
| `oraculo/visual.py` | geometria dos gráficos, em Python puro. Não sabe o que é azul |
| `oraculo/guardado.py` | onde `data/` mora. **Todo arquivo carimba a hora em que nasceu** |
| `api/index.py` | as duas páginas e o JSON cru |
| `scripts/calibrar.py` | mede a calibração sobre mercados resolvidos |
| `scripts/montar.py` | monta o painel dos mercados abertos |
| `scripts/testar.py` | casos-limite das funções puras, sem rede. **Portão** |
| `scripts/auditar.py` | invariantes do dado real. **Portão** |

### Os dados

| arquivo | o que é | quem grava |
|---|---|---|
| `data/calibragem.json` | a calibração nos três horizontes | `scripts/calibrar.py` |
| `data/painel.json` | os mercados abertos com taxa-base | `scripts/montar.py` |

---

## Armadilhas conhecidas

Todas estas aconteceram de verdade, quase todas no dia em que o projeto foi
escrito. Cada uma tem um caso em `scripts/testar.py`.

### 1. "Não achei" e "não consegui" são coisas diferentes

O modo de falha que este projeto mais teme. Casos reais:

- **A Gamma devolve no máximo 100 itens**, para `limit=100`, `limit=200` ou
  `limit=500`. Não recusa o pedido maior, não avisa, não manda cabeçalho de
  página. A paginação parava na página "menor que o pedido", o que com teto real
  de 100 e pedido de 500 acontece na PRIMEIRA volta: "buscando até 2.500
  mercados" imprimia "100 vieram da Gamma" e a calibragem saía medida sobre 1/25
  da amostra, com todos os números com cara de certos.
- **A Gamma recusa `offset + limit > 2100`** com 422. Isso é diferente de "não há
  mais mercados", e por isso `Colheita` carrega o MOTIVO da parada até a tela.
- O `urllib` do Python toma 403 de intermediários que filtram por User-Agent, e
  esse 403 se parece com "o mercado não existe" para quem lê o log depressa.

**Sempre que uma leitura puder falhar, o `null` tem de sobreviver até a decisão.**
`?? 0` e `or 0` são quase sempre um bug.

### 2. Zero é uma afirmação

"A história diz que isto nunca acontece" e "não tenho amostra" são frases
opostas, e as duas saem como `0.0` se ninguém tomar cuidado.

O caso real: a família "nível do alvo no fim do ano" media "exatamente 4,25%"
como zero trajetórias. O zero era verdadeiro sobre a amostra e falso sobre o
mundo — **nenhuma das 43 variações anuais do alvo é exatamente +0,50**, e os
vizinhos de 25 pontos-base têm três cada. É buraco de histograma, não
impossibilidade. Hoje essa variante levanta `SemResolucao` e a página escreve o
motivo.

O outro caso: a família "sem mudança na reunião" passava um filtro sobre eventos
que nunca casava, contava zero e publicava **0,0%** para o desfecho mais comum
do conjunto, que é 48,9%.

### 3. Um retrato velho ao lado de um número novo

Todo arquivo de `data/` carimba a hora em que nasceu, e as duas páginas mostram
esse carimbo. Um mercado pode andar 30 pontos entre duas execuções.

E há **duas** datas que importam, não uma: a calibragem mostra quando foi medida
E sobre que janela de mercados. Uma janela antiga com carimbo de hoje é pior que
nenhum carimbo.

### 4. Sigla de três letras cabe dentro de meio dicionário

O filtro de "isto tem cara de economia" testava `chave in pergunta.lower()`, e a
lista de órfãos veio com "Communist Party of the Russian **Fed**eration" e
"Phili**ppi**nes military clash". Use `\b`.

### 5. `NaN` fura guardas

`NaN <= 0` e `NaN >= 0` são **ambos falsos**. Um guard escrito como
`if x < 0: return` deixa NaN passar, e daí o Brier inteiro vira NaN. Compare com
`x == x` ou `math.isfinite`.

### 6. A troca de separador decimal come as unidades

`f"{x:+.1f} p.p.".replace(".", ",")` publicou **"+54,7 p,p,"** na tela. A troca
tem de acontecer ANTES de a unidade ser grudada. Ver `_decimal` em
`api/index.py`.

### 7. A decomposição de Murphy não fecha com preço contínuo

`Brier = confiabilidade − resolução + incerteza` só vale quando cada faixa tem um
ÚNICO valor de previsão. Com preço contínuo em baldes de dez pontos sobra a
variação dentro do balde, e a identidade erra por ~0,0007 — pequeno o bastante
para tentar a gente a afrouxar a tolerância do auditor.

A saída certa foi nomear o número contra o qual ela fecha de verdade
(`brier_das_faixas`), e a diferença entre os dois virou informação: é quanto o
mercado ganha por precificar 0,37 em vez de "algo entre 0,3 e 0,4".

### 8. A taxa-base não é previsão

A armadilha conceitual, e a mais fácil de cair. O Fed subiu juros em 48,8% dos
anos desde 1983; isso **não** quer dizer que a chance de alta em 2026 seja 48,8%.
2026 não é um ano sorteado do chapéu — tem uma inflação medida e um comitê que já
falou. O mercado sabe disso, a taxa-base não sabe nada disso.

A taxa-base serve para dar ESCALA ao preço, e é assim que a página a apresenta.
Se alguém um dia escrever "distância grande = oportunidade", o projeto virou
outra coisa.

---

## Como escrever código aqui

**Comentário explica POR QUE, com número.** Quase todo corte tem a medição que o
justifica escrita ao lado, e quando não tem, diz que não tem. Um comentário que
repete o que o código faz é pior que nenhum.

Exemplo do tom (de `oraculo/fontes/polymarket.py`):

```
# MEDIDO em 11/09/2026: a Gamma devolve 100 itens para `limit=100`, `limit=200` e
# `limit=500`. Ela não recusa o pedido maior, não avisa, não manda cabeçalho de
# página — simplesmente entrega 100.
```

**Outras convenções:**

- Código e comentários **em português**. Nomes de variáveis também.
- Sem framework de teste. Funções puras se testam com um script em `scripts/`
  que chama e imprime — ver `scripts/testar.py`.
- `python -m scripts.testar` e `python -m scripts.auditar` antes de commitar.
  Os dois respondem perguntas diferentes: o primeiro pergunta "o código está
  certo?" com entradas inventadas, o segundo "o dado que saiu faz sentido?" com
  o dado real.
- Cores de gráfico e painel: use a skill `dataviz` e **rode o validador**. O par
  em uso passou nos seis testes nos dois modos (ΔE de CVD 24,7 claro / 26,8
  escuro).
- Mensagem de commit: título curto no imperativo, corpo explicando **o que foi
  medido** e **o que mudou de comportamento**.

---

## O estado, em uma linha

O que funciona: a medição de calibração, o catálogo de famílias com as fontes
declaradas, os dois portões, e a honestidade sobre o resto.

O que **não** está demonstrado: que exista mercado mal precificado aqui. A
calibragem mede que o Polymarket acerta, e o único desvio que separa foi achado
depois de olhar os dados.

**Não transforme a coluna "distância" em recomendação enquanto a calibragem
disser o que ela diz hoje.**
