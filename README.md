# 🎸 Tom — agente de atendimento da Empório da Música

Protótipo de agente de atendimento por mensagens de texto para a **Empório da Música**, loja fictícia de
instrumentos musicais em Campo Grande/MS. O agente ("Tom") responde dúvidas recorrentes de clientes:
catálogo, preços, promoções, status de pedido, trocas e devoluções, horários, pagamento e frete.
Ele decide sozinho quando consultar **dados** (CSVs) e quando consultar **políticas** (manual em PDF).

- **Abordagem:** agente com *function calling* (tool use) e 9 ferramentas determinísticas em Python
- **Modelo:** Google Gemini 2.5 Flash (free tier do Google AI Studio)
- **Interface:** CLI com histórico persistente por sessão
- **Exemplos de conversa:** [`examples/`](examples/)

---

## Sumário

1. [Como rodar](#como-rodar)
2. [Arquitetura](#arquitetura)
3. [Decisões técnicas](#decisões-técnicas)
4. [Tratamento dos dados e suposições](#tratamento-dos-dados-e-suposições)
5. [Exemplos de interação](#exemplos-de-interação)
6. [Limitações conhecidas e próximos passos](#limitações-conhecidas-e-próximos-passos)
7. [Uso de assistentes de código](#uso-de-assistentes-de-código)

---

## Como rodar

Requisitos: Python 3.10+ e uma chave gratuita da API do Gemini
([Google AI Studio → Get API key](https://aistudio.google.com/apikey)).

```bash
git clone https://github.com/Albshoji/case-artefact.git
cd case-artefact

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # e preencha GEMINI_API_KEY no .env
```

### Conversar com o agente

```bash
python -m emporio                  # nova conversa
python -m emporio --debug          # mostra as ferramentas chamadas e o que retornaram
python -m emporio --sessao maria   # cria/retoma a conversa "maria" (histórico salvo em .sessions/)
```

Comandos dentro do chat: `/nova` (reinicia a conversa), `/debug` (liga/desliga o rastro de ferramentas), `/sair`.

### Variáveis de ambiente (`.env`)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GEMINI_API_KEY` | sim | Chave do Google AI Studio |
| `GEMINI_MODEL` | não | Modelo (padrão `gemini-2.5-flash`) |
| `AGENT_TODAY` | não | Fixa a "data de hoje" do agente (`YYYY-MM-DD`). Útil porque os pedidos do CSV são de out/2025 a mar/2026 — com `AGENT_TODAY=2026-03-25` os status e prazos ficam coerentes |
| `AGENT_TIME` | não | Fixa a hora (`HH:MM`), para testar o comportamento fora do expediente |

### Testes e exemplos

```bash
pytest                             # 31 testes, sem rede (ferramentas + loop do agente com modelo falso)
python scripts/gerar_exemplos.py   # regenera examples/*.md rodando o agente de verdade
```

---

## Arquitetura

```
                    ┌────────────────────────────────────────────────┐
 Cliente ──texto──▶ │ CLI (emporio/cli.py)                           │
                    │   └─ Agent.send()  (emporio/agent.py)          │
                    │        │  histórico + system prompt dinâmico   │
                    │        ▼                                       │
                    │   Gemini 2.5 Flash ──function call──┐          │
                    │        ▲                            ▼          │
                    │        └──── resultado JSON ── tools.execute() │
                    └───────────────────────────────────┬────────────┘
                                                        │
          ┌──────────────────────────┬──────────────────┼─────────────────────┐
          ▼                          ▼                  ▼                     ▼
   store.py (CSVs)          policies.py (manual)   cálculos de regra     logs/encaminhamentos.jsonl
   produtos, promoções,     knowledge/politicas.md  PIX, parcelas, frete,  (handoff p/ equipe humana)
   pedidos, clientes        10 seções por tópico    prazos de devolução
```

| Arquivo | Responsabilidade |
|---|---|
| `emporio/store.py` | Carrega e normaliza os CSVs; preço efetivo, disponibilidade, busca tolerante a acentos/plurais/modelos (`GD-20` = `GD20`), verificação de cliente |
| `emporio/tools.py` | As 9 ferramentas expostas ao LLM + seus schemas |
| `emporio/policies.py` + `knowledge/politicas.md` | Manual de políticas estruturado por tópico |
| `emporio/prompts.py` | Persona, regras e contexto temporal (data, hora, loja aberta/fechada) |
| `emporio/agent.py` | Loop de function calling, retries, persistência do histórico |
| `emporio/cli.py` | Interface de terminal |

### Ferramentas

| Ferramenta | Quando o agente usa |
|---|---|
| `buscar_produtos` | Buscas abertas com filtros (categoria, termo, faixa de preço, só disponíveis) |
| `detalhes_produto` | Produto específico: preço, promoção ativa/encerrada, specs, alternativas se indisponível |
| `listar_categorias` | "O que vocês vendem?" / checar se há estoque numa categoria (ex.: violino) |
| `listar_promocoes_ativas` | "Tem alguma promoção?" |
| `calcular_condicoes_pagamento` | Preço no PIX e parcelamento máximo segundo as regras de parcela mínima |
| `calcular_frete` | Frete e prazo (Campo Grande: regra fixa; outras cidades: modalidades + cotação) |
| `consultar_politicas` | Endereço, horário, pagamento, trocas, frete, rastreio, promoções, garantia, LGPD |
| `consultar_pedido` | Status, itens, rastreio e **prazos de devolução/troca/garantia já calculados** — exige e-mail ou telefone |
| `encaminhar_para_equipe` | Reclamação, devolução, atraso, cotação, pedido de humano → gera protocolo |

---

## Decisões técnicas

### 1. Abordagem: function calling com ferramentas determinísticas (sem RAG vetorial, sem agente SQL)

A pergunta central do desafio é "o agente sabe **quando** consultar dados e **quando** consultar políticas?".
Function calling responde isso de forma explícita e auditável: cada consulta aparece como uma chamada
nomeada (veja os blocos ⚙️ nos [exemplos](examples/)).

- **Por que não RAG vetorial para as políticas?** O manual tem ~3 mil tokens e 10 seções bem delimitadas.
  Embeddings + chunking + banco vetorial adicionariam infraestrutura e o risco de cortar uma regra no meio
  (ex.: a tabela de parcelamento separada das exceções), sem ganho de recall. Em vez disso, o PDF virou
  um markdown curado (`knowledge/politicas.md`) e o modelo escolhe o **tópico** (enum) — o "retriever" é
  o próprio LLM, com 100% de precisão sobre qual seção foi lida. Se o manual crescer para dezenas de
  páginas, a mesma interface `consultar_politicas` pode passar a usar busca híbrida (BM25 + embeddings)
  sem mudar o resto do agente.
- **Por que não um agente text-to-SQL?** Dá flexibilidade, mas expõe o modelo ao esquema bruto
  (`status=coming_soon`, `is_active=0`, `credit_6x`) e deixa regras de negócio por conta dele — por
  exemplo, aplicar promoção mas não acumular PIX, ou contar 7 dias do recebimento e 30 dias da compra.
  Também abre espaço para vazar dados de outros clientes. Com ferramentas, **as regras ficam em Python,
  testadas**, e o LLM só decide o que consultar e como comunicar.
- **Contas fora do LLM.** Preço promocional, preço no PIX, parcelamento com parcela mínima por faixa,
  frete e "quantos dias desde a entrega" são calculados em código. LLMs erram aritmética e datas; isso
  num atendimento vira propaganda enganosa (o próprio manual alerta para isso).
- **Loop manual** em vez do *automatic function calling* do SDK: permite limitar passos (8 rodadas por
  mensagem), capturar o rastro das chamadas (debug e exemplos), tratar erro de ferramenta sem derrubar a
  conversa e fazer *rollback* do histórico se a API falhar.

### 2. Modelo e provedor: Gemini 2.5 Flash (Google AI Studio, free tier)

- Gratuito para prototipar, com function calling nativo e paralelo, bom português e baixa latência — o
  que importa num canal tipo WhatsApp.
- Um modelo "flash" é suficiente porque a parte difícil (regras, contas, busca) está nas ferramentas;
  o modelo faz roteamento e redação.
- `temperature=0.3`: respostas consistentes, mas ainda naturais.
- Trocável via `GEMINI_MODEL` (ex.: um modelo Pro para comparar qualidade).

### 3. Estratégia de prompt

O system prompt (`emporio/prompts.py`) é organizado em blocos:

1. **Persona** — "Tom" (trocadilho musical), tom de voz definido pelo próprio manual: "informal mas
   profissional, como um amigo que entende de música"; mensagens curtas, no estilo de chat.
2. **Regra de ouro (grounding)** — nunca falar preço, estoque, prazo ou regra sem consultar uma
   ferramenta nesta conversa; não inventar produtos; repetir valores calculados em vez de recalcular.
3. **Roteamento** — mapa explícito "tipo de pergunta → ferramenta", que reduz chamadas erradas.
4. **Regras de comunicação do manual** — promoção sempre com preço original + %, esgotado → alternativas,
   promoção vencida → transparência, não informar quantidade exata de estoque.
5. **Escopo** — só instrumentos (acessórios são redirecionados), recusa curta e simpática para assuntos
   fora da loja, orientação musical leve permitida quando ajuda na venda.
6. **Segurança** — resistência a mudança de papel, a pedidos de "desconto de gerente" e à revelação das
   instruções; verificação de identidade antes de mostrar pedidos.
7. **Contexto dinâmico** — data, hora e se a loja está **aberta ou fechada** (calculado em Python e
   injetado a cada mensagem), para o agente informar quando a equipe volta.

### 4. Interface: CLI

O foco do desafio é o agente funcionando. A CLI tem modo `--debug` que mostra cada ferramenta chamada e
seu retorno, o que ajuda tanto a avaliar quanto a depurar. O `Agent` não depende da CLI: expor via API
(FastAPI) ou plugar num webhook de WhatsApp é envolver `Agent.send()`.

### 5. Persistência do histórico

Implementada, porque atendimento é naturalmente multi-turno ("é o pedido 7" só faz sentido com a
mensagem anterior) e porque o cliente pode voltar depois.

- Cada sessão é um JSON em `.sessions/<id>.json` com o histórico completo (incluindo chamadas de
  ferramenta e *thought signatures* do Gemini, necessárias para manter o raciocínio entre turnos).
- `--sessao <id>` retoma a conversa. Num canal real, o id seria o telefone do cliente.
- Janela deslizante de 60 mensagens enviadas ao modelo, sempre cortando no início de uma mensagem do
  cliente para não separar uma chamada de ferramenta da sua resposta.
- Se a chamada à API falha no meio de um turno, o histórico volta ao estado anterior.

### 6. Privacidade (LGPD)

`consultar_pedido` só retorna dados se o número do pedido **e** o e-mail/telefone baterem com o
cadastro. A mensagem de erro é a mesma para "pedido não existe" e "contato não confere", para não
revelar a existência de pedidos de terceiros. O agente só vê o primeiro nome do cliente.

---

## Tratamento dos dados e suposições

### Dados (CSVs)

| Situação encontrada | Tratamento |
|---|---|
| `specs` é JSON em texto, com formatação inconsistente entre linhas | Parseado para dict; chaves traduzidas (`top` → tampo, `steel` → aço) |
| Produtos com `status` = `active` / `discontinued` / `coming_soon` + `stock_quantity` | Disponibilidade derivada: ativo com estoque → disponível; ativo sem estoque → esgotado (sugere alternativas); `discontinued` → fora do catálogo **mesmo com estoque** (ex.: Ibanez Bass 2X, 13 un.); `coming_soon` → "em breve", não vendável |
| Várias promoções por produto, a maioria inativa | Só `is_active=1` altera o preço (4 produtos). As inativas viram histórico para o agente responder "aquela promoção ainda vale?" com transparência |
| Filtro "até R$ X" | Considera o **preço efetivo** (com promoção), sem o desconto do PIX |
| Pedidos sem data real de entrega | Para pedidos `delivered`, a data de recebimento considerada é `estimated_delivery` (e o agente é avisado disso) |
| Telefones em formatos variados | Comparação só pelos dígitos finais (aceita com ou sem DDD) |
| Categorias 6, 7 e 8 (sopros e cordas orquestrais) sem nenhum produto | O agente informa que não há opções no momento, em vez de dizer que a loja "não vende" |
| Buscas com acento, plural ou modelo escrito diferente | Normalização (sem acento, minúsculas, singular simples) e comparação "compacta" (`GD-20` = `GD20`) |

Inconsistências detectadas e **não** corrigidas (o agente apresenta o valor do sistema):

- Pedidos 3 e 14 contêm o produto 130 (Kala KA-ABP-CTG), que está como `coming_soon`.
- O total de dois pedidos não bate com a soma dos preços de tabela atuais: pedido 3 (R$ 3.450 vs. 2 × R$ 1.749)
  e pedido 20 (R$ 1.400 vs. R$ 799 + R$ 689). Pode ser desconto da época ou erro de cadastro; o agente
  informa o total registrado no pedido.

### Manual de políticas (PDF)

Convertido manualmente para `knowledge/politicas.md`, revisado e dividido em 10 tópicos. Inconsistências
resolvidas (também anotadas no próprio arquivo):

1. **Telefone:** capa e tabela de dados da empresa trazem (67) 3341-4444 (telefone/WhatsApp); a seção 7
   cita (67) 3321-4500. Adotado **(67) 3341-4444**, que aparece duas vezes, inclusive na tabela oficial.
2. **E-mail:** a seção 1.2 traz `contato@empóriodamusica.com.br` (com acento) e a capa traz sem acento.
   Adotado **sem acento** (provável erro de digitação).
3. **Parcelamento:** a tabela diz "parcela mínima R$ 100" para crédito, mas a seção 3.1 detalha faixas.
   Adotadas as faixas da 3.1 (mais específicas): 2–3x mín. R$ 50 (interpretação de "sem valor mínimo
   (exceto abaixo de R$ 50,00)"), 4–6x mín. R$ 80, 7–12x mín. R$ 100.

### Outras suposições

- **Data de referência:** os dados são um retrato de março/2026. Os exemplos usam `AGENT_TODAY=2026-03-25`
  (quarta, 10:30). Sem a variável, o agente usa a data real.
- **Região metropolitana de Campo Grande** = cidade de Campo Grande (o manual não lista municípios).
  Para as demais cidades, o frete é "sob cotação", porque não temos a tabela dos Correios/Jadlog.
- **Feriados** não são considerados no cálculo de loja aberta/fechada.
- **Lojas parceiras de acessórios:** o manual pede para sugeri-las "quando possível", mas não lista
  nenhuma. O agente sugere genericamente uma loja especializada, sem inventar nomes.
- **Encaminhamento humano:** como não há sistema de tickets, os casos são gravados em
  `logs/encaminhamentos.jsonl` com protocolo, simulando o handoff para a equipe.
- O agente atende o cliente final (não a equipe), seguindo o fluxo do manual (seção 7.2).

---

## Exemplos de interação

Conversas reais geradas com `scripts/gerar_exemplos.py`, com as chamadas de ferramenta visíveis:

| Arquivo | Cenário |
|---|---|
| [01_catalogo_violoes](examples/01_catalogo_violoes.md) | Violões até R$ 1.000 disponíveis → recomendação para iniciante → parcelas e PIX |
| [02_preco_e_promocao_encerrada](examples/02_preco_e_promocao_encerrada.md) | Preço do Takamine GD20 → cliente cita promoção que já acabou → promoções ativas |
| [03_devolucao_arrependimento](examples/03_devolucao_arrependimento.md) | **Não trivial:** "me arrependi" → verificação de identidade → pedido fora do prazo de 7 dias → explica garantia legal ainda vigente |
| [04_pedido_atrasado_encaminhamento](examples/04_pedido_atrasado_encaminhamento.md) | **Não trivial:** pedido enviado com previsão vencida → empatia → protocolo para a equipe |
| [05_institucional_e_fora_de_escopo](examples/05_institucional_e_fora_de_escopo.md) | Endereço e horário → acessórios (não vende) → violino (sem estoque) → assunto fora do escopo → tentativa de manipulação |

---

## Limitações conhecidas e próximos passos

**Limitações**

- **Avaliação manual.** A qualidade das respostas foi verificada lendo os exemplos; os testes
  automatizados cobrem ferramentas e loop, não o comportamento do LLM.
- **Free tier do Gemini** tem limite de requisições por minuto/dia; sob carga, o agente faz *retry* com
  backoff, mas não há fila.
- **Busca por palavra-chave**, não semântica: "violão bom pra igreja" não é mapeado para um tipo de
  instrumento. O LLM compensa reescrevendo a busca, mas pode falhar.
- **Sem cálculo de frete por CEP** e sem saber feriados.
- **Encaminhamento simulado** (arquivo JSONL), sem integração real com a equipe.
- **Dados em memória**, carregados uma vez: alterações nos CSVs exigem reiniciar o agente.
- **Identidade:** num WhatsApp real o telefone do remetente já identificaria o cliente; aqui ele precisa
  digitar e-mail/telefone.

**Com mais tempo, eu faria:**

1. **Suíte de avaliação do agente** (LLM-as-judge + asserts): ~50 perguntas com respostas esperadas,
   medindo escolha de ferramenta correta, *groundedness* (todo preço citado veio de uma ferramenta),
   recusa de fora do escopo e resistência a *prompt injection*. Rodar a cada mudança de prompt/modelo.
2. **Guardrail de saída:** checar por regex que todo valor `R$` da resposta aparece em algum retorno de
   ferramenta do turno; se não, regenerar.
3. **Integração com WhatsApp** (Cloud API) via FastAPI + webhook, com sessão pelo telefone e Redis/Postgres
   no lugar dos JSONs.
4. **Banco de dados real** (Postgres) no lugar dos CSVs e busca semântica/híbrida no catálogo.
5. **Handoff real:** abrir ticket no sistema da equipe e avisar o cliente quando for respondido.
6. **Observabilidade:** tracing das chamadas (Langfuse/OpenTelemetry), custo e latência por conversa.
7. **Painel para a equipe** com as conversas encaminhadas e as perguntas que o agente não soube responder,
   para melhorar políticas e catálogo.

---

## Uso de assistentes de código

Usei o **Claude Code** (CLI da Anthropic, modelo Claude Opus 5.5) como par de programação durante todo o
projeto. O fluxo foi:

1. **Leitura e diagnóstico:** o Claude Code leu o enunciado, o manual em PDF e os CSVs, e listou as
   inconsistências dos dados (produtos `coming_soon` em pedidos, totais divergentes, telefone e e-mail
   duplicados no manual, regras de parcelamento conflitantes).
2. **Decisões:** discutimos a arquitetura (function calling vs. RAG vs. SQL) e eu escolhi o provedor
   (Gemini, pelo free tier).
3. **Implementação incremental:** camada de dados → ferramentas com testes → prompt e loop do agente →
   CLI → exemplos → README, com um commit por etapa.
4. **Validação:** rodei a suíte de testes e as conversas reais. Revisei as transcrições para checar se os
   valores citados batiam com os dados e ajustei prompt e ferramentas onde o comportamento não estava bom.

O assistente acelerou a escrita de código e documentação. As decisões de produto (persona, como tratar
as inconsistências, o que é fora do escopo, quando escalar para humano) foram revisadas por mim.

---

## Estrutura do repositório

```
├── data/                       # dados fornecidos (CSVs + manual em PDF)
├── knowledge/politicas.md      # manual convertido e curado, por tópico
├── emporio/                    # código do agente
│   ├── agent.py  cli.py  config.py  policies.py  prompts.py  store.py  tools.py
├── examples/                   # conversas de exemplo (geradas pelo agente)
├── scripts/gerar_exemplos.py
├── tests/                      # pytest (sem rede)
├── requirements.txt  .env.example
```
