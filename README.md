# Oráculo

Projeção de preço de **bitcoin, ouro, prata, petróleo, ether e gás**, e de
**juros, inflação e recessão** — o que o [Polymarket](https://polymarket.com)
precifica hoje, ao lado do que a história do próprio ativo registrou. E, antes de
tudo, a medição de se o preço do mercado merece confiança.

**Sem nenhuma chave de API.** Gamma e CLOB do Polymarket; `fredgraph.csv` do FRED
para petróleo, bitcoin, gás e as séries do Fed, do CPI e do NBER; a
[LBMA](https://www.lbma.org.uk) para ouro e prata, desde 1968. Não há `.env`,
banco nem serviço pago: o estado inteiro são dois arquivos JSON versionados no
repositório.

```bash
pip install -r requirements.txt
python -m scripts.calibrar        # mede a calibração  (~10 min)
python -m scripts.montar          # monta o painel     (~20 s)
uvicorn api.index:app --reload    # http://127.0.0.1:8000
```

---

## A ideia

Para "o bitcoin toca US$ 150 mil até 31 de dezembro?" existe uma referência
histórica quase literal:

- o bitcoin está em **S₀** hoje;
- faltam **h** dias até a data;
- a pergunta é se ele sobe **alvo/S₀** em algum momento desses h dias.

Então o Oráculo varre a série inteira do ativo, pega toda janela de h dias, e
conta em quantas delas o preço fez esse mesmo movimento. É reamostragem
empírica: **não supõe distribuição nenhuma**, o que importa muito porque bitcoin
e petróleo têm cauda gorda, e toda conta que supõe uma normal subestima
justamente o extremo que estes mercados perguntam.

Esse número vai para a tela ao lado do preço do mercado. Os dois são estimativas
da mesma probabilidade, feitas de jeitos independentes: o mercado sabe o que é
específico de agora, a história sabe o que costuma acontecer. A distância entre
eles é a informação.

**E a pergunta que o projeto começou querendo responder** — *dá para achar
mercado mal precificado comparando preço com frequência histórica?* — teve
resposta medida: **quase sempre não**. Está tudo abaixo.

---

## O que foi medido

### 1. O Polymarket é quase perfeitamente calibrado

Um preço de contrato binário *é* uma probabilidade: pagar US$ 0,70 por um papel
que vale US$ 1 se o evento acontecer é dizer 70%. Dá para conferir isso contra o
mundo sem usar modelo nenhum — basta pegar mercados já resolvidos, ver quanto
custavam antes do fim, e contar.

Amostra: **2.023 mercados resolvidos**, os de maior volume do Polymarket, com
volume acima de US$ 20 mil. Sete dias antes da resolução:

| | valor | o que significa |
|---|---|---|
| Brier | **0,0841** | erro quadrático médio; 0 é perfeito |
| Brier da climatologia | 0,1778 | chutar sempre a taxa-base da amostra (23,1%) |
| ganho sobre a climatologia | **+52,7%** | o mercado sabe MUITO mais que "isto é raro" |
| **confiabilidade** | **0,0013** | quão longe o preço fica da frequência observada |
| resolução | 0,0931 | quanto o preço se compromete em vez de responder a média |

**A confiabilidade de 0,0013 é o número que derruba a tese original.** O preço
fica a três milésimos da frequência observada. Não há viés sistemático para
corrigir.

A curva, faixa por faixa:

| faixa | n | pediu | aconteceu | erro |
|---|---|---|---|---|
| 0,0–0,1 | 1023 | 0,011 | 0,022 | +1,1 p.p. |
| 0,1–0,2 | 93 | 0,150 | 0,237 | +8,7 p.p. |
| 0,2–0,3 | 73 | 0,249 | 0,315 | +6,6 p.p. |
| 0,3–0,4 | 52 | 0,355 | 0,442 | +8,7 p.p. |
| 0,4–0,5 | 94 | 0,455 | 0,436 | −1,8 p.p. |
| 0,5–0,6 | 92 | 0,544 | 0,489 | −5,5 p.p. |
| 0,6–0,7 | 76 | 0,653 | 0,684 | +3,1 p.p. |
| 0,7–0,8 | 48 | 0,747 | 0,792 | +4,4 p.p. |
| 0,8–0,9 | 36 | 0,845 | 0,917 | +7,1 p.p. |
| 0,9–1,0 | 91 | 0,981 | 0,978 | −0,3 p.p. |

### 2. O viés favorito–azarão não aparece

A literatura de pista de corrida acha o mesmo padrão desde os anos 1940:
apostador paga demais por probabilidade baixa e de menos por probabilidade alta.
Se ele existisse aqui, a ponta de baixo mostraria erro NEGATIVO e a de cima,
POSITIVO.

Medido a 7 dias: azarão (< 0,20) **+0,017** sobre n = 1.116; favorito (> 0,80)
**+0,018** sobre n = 127. **As duas pontas erram para o mesmo lado e por nada.**
O viés não está lá.

### 3. O único desvio que separa foi escolhido depois de ver os dados

A banda 0,10–0,40 erra para o mesmo lado nos três horizontes:

| horizonte | n | pediu | aconteceu | diferença | z |
|---|---|---|---|---|---|
| 1 dia | 305 | 0,247 | 0,331 | **+0,085** | +3,43 |
| 7 dias | 218 | 0,232 | 0,312 | **+0,080** | +2,79 |
| 30 dias | 209 | 0,229 | 0,316 | **+0,086** | +2,97 |

Três amostras diferentes, três vezes o mesmo número. É o achado mais forte do
projeto, e ele vem com **duas ressalvas que o derrubam como conclusão**:

- **A janela foi escolhida depois de olhar.** Ela saiu de ver o erro apontar para
  o mesmo lado nas três faixas. Escolher a janela depois de ver os dados infla
  qualquer teste feito sobre ela.
- **O z supõe independência que não existe.** Um evento de múltiplas opções
  ("quem vence?" com cinquenta nomes) vira cinquenta mercados binários que
  resolvem JUNTOS. O n efetivo é o número de eventos, e é bem menor que 218.

Fica registrado como **hipótese para a próxima medição**, não como achado. E o
painel não o transforma em recomendação.

---

## O que a página mostra

Duas telas.

**O painel** põe três números lado a lado para cada mercado coberto:

- **preço** — a probabilidade que o mercado atribui hoje;
- **taxa-base** — a frequência histórica, pela janela de preço acima ou por uma
  série do FRED;
- **ajustado** — o preço passado pela curva de confiabilidade medida acima.

**Para as famílias de calendário, a taxa-base não é previsão — e essa é a ideia
mais fácil de entender errado aqui.** O Fed subiu juros em 48,8% dos anos desde
1983; isso não quer dizer que a chance de alta em 2026 seja 48,8%, porque 2026
não é um ano sorteado do chapéu. Ali a taxa-base serve para dar **escala**: um
mercado a 0,88 ao lado de uma referência de 0,49 diz *o mercado acha este ano
quase duas vezes mais propenso a alta que um ano típico dos últimos quarenta*.

**Para as famílias de preço a referência é bem mais forte**, porque ela é do
próprio ativo e no próprio horizonte da pergunta. Continua sem saber nada sobre o
ciclo em curso — mas "em 14,5% das janelas de 110 dias o bitcoin subiu os 94% que
levariam a US$ 150 mil" é uma frase sobre o bitcoin, não sobre o calendário.

**A segunda tela é a calibragem**, com os três horizontes lado a lado. Ela vem
primeiro na ordem de importância: se o mercado é bem calibrado, o preço dele já é
a melhor previsão disponível e qualquer número ao lado é enfeite.

---

## As famílias do catálogo

Casar uma pergunta do Polymarket com uma série é feito **à mão, uma família por
vez**, em `oraculo/catalogo.py`. Não há inferência automática e não deve haver.

### Preço de ativo

| família | o que responde |
|---|---|
| Preço: toque para cima | "hit / reach $X by DATE" — o ativo ENCOSTA no nível em algum momento |
| Preço: toque para baixo | "dip / fall to $X by DATE" — o mesmo, para baixo |
| Preço: acima na data | "be above $X **on** DATE" — onde o preço TERMINA |
| Preço: abaixo na data | o espelho |
| Preço: nova máxima histórica | o alvo é o maior preço que a série já registrou |

Ativos: bitcoin e ether (`CBBTCUSD`, `CBETHUSD`), WTI e Brent (`DCOILWTICO`
desde 1986, `DCOILBRENTEU` desde 1987), gás natural (`DHHNGSP`), ouro e prata
(LBMA, desde 1968).

Alguns números medidos em 12/09/2026, com o bitcoin a US$ 77.276 e 110 dias até
o fim do ano:

| mercado | preço | história |
|---|---|---|
| Bitcoin toca US$ 100 mil | 21,5% | **49,5%** |
| Bitcoin toca US$ 150 mil | 2,2% | **14,6%** |
| Bitcoin cai a US$ 45 mil | 9,5% | **9,4%** |
| Petróleo WTI toca US$ 110 em setembro | 34,5% | **8,7%** |
| Petróleo faz nova máxima histórica | 14,0% | **4,0%** |
| Ouro toca US$ 6.000 | 9,5% | **2,9%** |

### Calendário macro

| família | fonte | taxa-base medida |
|---|---|---|
| Fed: alta na reunião | `DFEDTAR` + `DFEDTARU` | 25,8% das reuniões desde 1982 |
| Fed: corte na reunião | idem | 25,3% |
| Fed: sem mudança na reunião | idem | **48,9%** — o desfecho mais comum |
| Fed: alguma alta no ano | idem | 48,8% dos anos completos (1983–2025) |
| Fed: nenhum corte no ano | idem | 48,8% |
| Fed: exatamente N cortes no ano | idem | varia; 21 dos 43 anos têm zero |
| Fed: N cortes ou mais no ano | idem | idem |
| Fed: nível do alvo no fim do ano | idem | reamostragem das variações anuais |
| Inflação acima de X% no ano | `CPIAUCSL` | 29,5% dos anos passam de 5% |
| Recessão nos EUA no ano | `USREC` | 26,9% dos anos desde 1948 |

As três famílias por reunião somam exatamente **1,0000**, que é a conferência
escrita na própria justificativa delas.

O que **não** casa com nenhuma família aparece numa lista à parte na página, com
o volume de cada um. Sem essa lista, um mercado que o Oráculo deveria cobrir e
não cobre simplesmente sumiria da tela, indistinguível de um que não existe.

---

## As coisas que o projeto se recusa a afirmar

Três, e as três estão no código:

1. **Nível exato do alvo do Fed no fim do ano.** Nenhuma das 43 variações anuais
   do alvo é exatamente +0,50, então "exatamente 4,25%" daria zero trajetória —
   com os vizinhos de 25 pontos-base em três cada. É buraco de histograma, não
   impossibilidade, e publicá-lo como 0% seria dizer "a história diz que nunca
   acontece". A família levanta `SemResolucao` e a página escreve o motivo.
2. **Ajuste de preço em faixa com menos de 30 observações.** A coluna fica vazia
   em vez de devolver o preço de volta — "não medi" e "medi e deu igual" são
   coisas diferentes.
3. **Qualquer coisa parecida com sinal de compra.** A distância entre preço e
   taxa-base mede desacordo com um período típico, e desacordo quase sempre é o
   mercado sabendo de algo. O projeto não distingue os dois casos e não finge
   distinguir.

---

## Como fica de pé

- **Duas execuções no GitHub Actions**: o painel de hora em hora (~21
  requisições), a calibragem uma vez por dia (~2.100). As duas commitam `data/`.
- **Dois portões antes de todo commit**: `scripts/testar.py` (39 casos-limite,
  sem rede) e `scripts/auditar.py` (invariantes do dado real, incluindo a
  decomposição de Murphy fechando exatamente).
- **A página não calcula nada**: `api/index.py` lê os JSON e desenha. Uma função
  Python na Vercel, sem build de front-end e sem Node.
- **Todo arquivo carimba a hora em que nasceu**, e as duas telas mostram esse
  carimbo. O dado nasce velho por construção; a idade na tela é o que separa
  informação de informação errada.

Para mexer no código, leia [`AGENTS.md`](AGENTS.md) — em particular a seção de
armadilhas, que tem a lista de coisas que já quebraram e por quê.
