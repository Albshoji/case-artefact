# Como o código funciona

Explicação arquivo por arquivo do agente "Tom". As referências `arquivo:linha` batem com a versão atual
do código.

## Visão geral

```
você digita no terminal
   -> __main__.py lê a mensagem e chama agent.send()
      -> agent.py monta o prompt (prompts.py) e manda pro Gemini junto com as ferramentas
         -> o Gemini responde direto ou pede uma ferramenta
            -> o SDK roda a função Python pedida (tools.py) e devolve o resultado pro modelo
               (isso pode se repetir até 8 vezes)
         <- resposta final em texto
      <- agent.py salva o histórico em .sessions/<id>.json
   <- __main__.py imprime "Tom: ..."
```

A divisão de trabalho é esta:

- o modelo (Gemini) entende a pergunta, escolhe a ferramenta e escreve a resposta;
- o Python (`tools.py`) faz tudo que precisa estar certo: filtra o catálogo, calcula preço, PIX,
  parcelas e prazos, e confere a identidade do cliente.

## Tamanho

| Arquivo | Linhas | Sem linhas em branco |
|---|---:|---:|
| `emporio/tools.py` | 391 | 325 |
| `emporio/agent.py` | 92 | 78 |
| `emporio/prompts.py` | 91 | 76 |
| `emporio/__main__.py` | 41 | 33 |
| Código do agente | 615 | 512 |
| `tests/test_tools.py` | 143 | 100 |
| `tests/test_agent.py` | 59 | 44 |
| `scripts/gerar_exemplos.py` | 107 | 95 |
| Total em Python | 924 | 751 |

Fora do Python: `knowledge/politicas.md` (161 linhas, o manual convertido) e o `README.md`.

---

## 1. `emporio/tools.py`: dados, regras e ferramentas

É o arquivo principal. Quando ele é importado, lê os CSVs e o manual uma vez só e guarda tudo em
memória. São 65 produtos e 20 pedidos, então não precisa de banco de dados.

### Imports e constantes (linhas 1-13)

- Linhas 1-9: imports, todos da biblioteca padrão (`csv`, `json`, `re`, `unicodedata`, `datetime`,
  `zoneinfo` etc.). Este arquivo não depende de nenhuma biblioteca externa.
- Linha 11: `ROOT` é a pasta raiz do projeto, calculada a partir da localização do arquivo. Assim o
  código funciona de qualquer pasta.
- Linha 12: `LOGS_DIR` é onde ficam os encaminhamentos para a equipe (`logs/`).
- Linha 13: `TZ` é o fuso de Campo Grande. Toda data e hora do agente usa esse fuso, não o do computador.

### `now()` (linhas 16-27)

Devolve a data e a hora atuais no fuso de Campo Grande, com dois ajustes opcionais:

- se existir a variável de ambiente `AGENT_TODAY` (ex.: `2026-03-25`), troca a data (linhas 20-22);
- se existir `AGENT_TIME` (ex.: `10:30`), troca a hora (linhas 23-26).

O motivo está no comentário das linhas 17-18: os pedidos do CSV são de out/2025 a mar/2026. Com a data
real (nov/2026), todo pedido pareceria antigo e todo prazo de devolução estaria vencido. Fixar a data
deixa os exemplos e os testes coerentes e reproduzíveis.

### Leitura e texto (linhas 30-67)

- `ler_csv(nome)` (30-32): abre `data/desafio_tecnico_ai_eng - <nome>.csv` e devolve uma lista de
  dicionários, um por linha. Ex.: `{"product_id": "81", "name": "Yamaha C40...", ...}`. Tudo chega como
  texto; a conversão para número vem depois.

- `normalizar(texto)` (35-37): deixa o texto minúsculo e sem acento. `unicodedata.normalize("NFKD", ...)`
  separa a letra do acento ("ã" vira "a" + "~") e o `if not unicodedata.combining(c)` descarta o acento.
  `"Violão Elétrico"` vira `"violao eletrico"`, então o cliente pode escrever com ou sem acento.

- `compactar(texto)` (40-42): normaliza e tira tudo que não é letra ou número.
  `"Takamine GD-20"` vira `"takaminegd20"`. Serve para "GD-20", "gd 20" e "GD20" acharem o mesmo produto.

- `STOPWORDS` (45): palavras que não ajudam na busca ("de", "para", "com", "até"...). Sem essa lista,
  "violão para iniciante" daria ponto para qualquer produto com "para" na descrição.

- `SINONIMOS` (46-53): traduz o jeito do cliente falar para o jeito que está nos dados:
  - "eletroacústico", "eletroacústica", "elétrica" -> "eletrico" (nos dados, violão com captação aparece
    como "Elétrico");
  - "clássico" -> "nylon" (violão clássico é o de nylon);
  - "steel" -> "aco" (as especificações dizem `"strings": "steel"`);
  - "sintetizador" -> "synth".

- `palavras(texto)` (56-67): transforma um texto num conjunto de palavras comparáveis:
  1. normaliza e quebra em palavras (`re.findall(r"[a-z0-9]+", ...)`);
  2. pula as stopwords (59-60);
  3. faz um singular simples (61-65): "violões" -> "violao", "cordas" -> "corda" (tira o "s" final de
     palavras com mais de 3 letras);
  4. aplica os sinônimos (66).

  Exemplo: `palavras("Violões eletroacústicos")` devolve `{"violao", "eletrico"}`.

### Carga dos dados (linhas 70-118)

Este trecho roda uma vez, na importação.

- `CATEGORIAS` (72): `id -> nome` (`{5: "Violões", ...}`).
- `CLIENTES` (73): `id -> linha do cliente` (nome, telefone, e-mail, cidade).
- `PEDIDOS` (75-80): `id -> linha do pedido`. Cada pedido ganha uma lista `itens` vazia (77), preenchida
  em seguida com as linhas de `order_items.csv` (79-80).

- `PRODUTOS` (82-100): para cada linha de `products.csv`, monta um dicionário mais limpo:
  - converte preço para `float` e estoque para `int` (`or 0` protege contra campo vazio);
  - troca `category_id` pelo nome da categoria;
  - `specs` vem como JSON dentro do CSV (ex.: `{"top":"Spruce","strings":"nylon"}`) e vira dicionário
    com `json.loads`;
  - `promo` começa `None` e `promos_encerradas` começa vazia; as duas são preenchidas no trecho seguinte;
  - linhas 96-97: junta as especificações num texto e troca "electronics yes" por "eletrico", que é como
    o cliente pergunta;
  - linha 98, `busca`: o conjunto de palavras do produto (nome + categoria + descrição + specs),
    calculado uma vez para a busca ficar rápida;
  - linha 99, `nome_compacto`: o nome passado por `compactar`.

- Promoções (102-111): para cada linha de `promotions.csv`, se `is_active == "1"` ela vira a promoção
  ativa do produto; senão vai para `promos_encerradas`. As encerradas ficam guardadas de propósito
  (comentário da linha 110): quando o cliente pergunta "aquela promoção de 12% ainda vale?", o agente vê
  que ela existiu e já acabou.

- `POLITICAS` (113-118): lê `knowledge/politicas.md`, apaga os comentários `<!-- ... -->` (notas
  internas de curadoria) e divide o texto pelas linhas `## [topico] Título`. O resultado é
  `{"horario": "texto da seção...", "pagamento": "...", ...}`, com 10 tópicos. A expressão regular
  captura o nome entre colchetes e o texto até o próximo `## ` ou o fim do arquivo.

### Regras de negócio (linhas 121-182)

Todas as contas ficam aqui, para o modelo nunca precisar calcular nada.

- `brl(valor)` (121-123): formata como dinheiro brasileiro: `2199.0` -> `"R$ 2.199,00"`. O Python
  formata "2,199.00"; o código troca vírgula e ponto usando "#" como posição temporária.

- `preco_final(produto)` (126-129): o preço que o cliente paga. Com promoção ativa,
  `preço × (1 − desconto/100)` arredondado a 2 casas; sem promoção, o preço de tabela.

- `disponibilidade(produto)` (132-139): traduz status + estoque numa frase:
  - `discontinued` -> "descontinuado" (mesmo com estoque, como o Ibanez Bass 2X, que tem 13 unidades);
  - `coming_soon` -> "em breve";
  - estoque > 0 -> "disponível";
  - estoque 0 -> "esgotado no momento".

- `parcela_minima(n)` (142-149): a parcela mínima do manual para `n` vezes: 1x sem mínimo,
  2x-3x R$ 50, 4x-6x R$ 80, 7x-12x R$ 100.

- `max_parcelas(valor)` (152-157): testa de 2x a 12x e guarda o maior `n` em que `valor / n` respeita o
  mínimo. Exemplos:
  - R$ 599 -> 6x (599/6 ≈ 99,83 ≥ 80; 599/7 ≈ 85,57 < 100);
  - R$ 2.199 -> 12x;
  - R$ 90 -> 1x (90/2 = 45 < 50).

- `resumo_produto(produto)` (160-182): monta o que o modelo recebe sobre cada produto:
  - id, nome, categoria, disponibilidade e preço de tabela;
  - com promoção ativa (170-172): campanha, % e preço promocional, avisando que o PIX não dá desconto
    extra (promoções não acumulam);
  - sem promoção (173-174): o preço no PIX, com 5% de desconto;
  - parcelamento máximo já calculado (175), ex.: "até 12x de R$ 183,25 sem juros";
  - promoções encerradas, se houver (176-177);
  - "últimas unidades" quando restam 1 ou 2 (178-179). O manual pede para não informar a quantidade exata;
  - descrição e especificações (180-181), para o modelo justificar recomendações só com dados reais.

### As ferramentas (linhas 185-391)

São cinco funções Python comuns. O SDK do Gemini lê a assinatura (nomes e tipos dos parâmetros) e a
docstring de cada uma e gera sozinho a descrição que o modelo recebe. Por isso as docstrings são escritas
para o modelo: dizem quando usar a ferramenta e o que significa cada parâmetro.

O comentário das linhas 185-187 explica por que os parâmetros só usam tipos simples (`str`, `float`,
`int`, `bool`), com `""` e `0` no lugar de "vazio": o SDK não converte os argumentos do modelo para
`Literal[...]` nem um inteiro para `float | None`, e a chamada quebrava. As opções válidas (categorias,
tópicos, motivos) ficam escritas na docstring, e a ferramenta devolve a lista certa quando recebe um valor
inválido, para o modelo se corrigir sozinho.

#### `buscar_produtos` (linhas 189-242)

A única ferramenta de catálogo: preço, estoque, promoção, busca aberta e "o que tem em promoção".

Parâmetros:
- `termo`: o que o cliente digitou (marca, modelo, característica);
- `categoria`: uma das 9 categorias;
- `preco_max`: preço máximo (0 = sem limite);
- `so_promocoes`: só produtos com promoção ativa.

Passo a passo:
1. Categoria inválida (204-205): devolve a lista de categorias válidas.
2. Filtros (207-215): um laço por todos os produtos, com um `continue` para cada filtro (categoria,
   preço máximo, só promoções). O preço máximo é comparado com o preço com promoção: um produto de
   R$ 2.399 com 18% off entra em "até R$ 2.000".
3. Busca por texto (217-229), quando há `termo`:
   - primeiro tenta pelo nome compacto (219-222): se "takaminegd20" aparece dentro do nome compacto de
     algum produto, fica só com esses. É o caso de "quanto custa o Takamine GD-20?". Exige pelo menos
     4 caracteres, para um termo curto não casar com tudo;
   - senão (224-229), conta quantas palavras do termo cada produto tem (nas palavras de busca ou no nome
     compacto) e fica com os que têm a maior contagem. Em "violão nylon", os violões de nylon
     (2 acertos) ganham dos de aço (1 acerto).
4. Ordena do mais barato ao mais caro (231).
5. Separa disponíveis e indisponíveis (232-239):
   - `disponiveis`: até 10 produtos à venda, mais o total encontrado;
   - `indisponiveis`: só quando há `termo`. São os que batem com a busca mas não estão à venda (esgotado,
     descontinuado, em breve). Numa busca aberta ("violões até R$ 1000") só aparece o que dá para
     comprar, mas se o cliente pergunta por um modelo esgotado, o agente sabe que ele existe e pode dizer
     "esgotou, mas tenho estes parecidos".
6. Aviso (240-241) quando nada foi encontrado.

#### `calcular_pagamento` (linhas 245-264)

Para quando o cliente quer pagar vários produtos juntos. Para um produto só não precisa, porque o
`resumo_produto` já traz PIX e parcelas. Devolve:
- PIX com 5% de desconto, ou sem desconto se `preco_promocional=true`;
- parcelamento máximo;
- débito/boleto (preço cheio);
- `pode_combinar_formas`: o manual só deixa misturar PIX e cartão acima de R$ 2.000.

#### `consultar_politicas` (linhas 267-278)

Recebe um dos 10 tópicos do manual (listados na docstring) e devolve o texto inteiro da seção. Com um
tópico inválido, devolve a lista de tópicos válidos. Em vez de busca vetorial, o próprio modelo escolhe a
seção e recebe a regra completa, sem pedaços cortados.

#### `consultar_pedido` (linhas 281-360)

- `STATUS` (281-287): traduz os status do sistema (`shipped`, `delivered`...) para frases em português.
- `PAGAMENTOS` (289): nomes das formas de pagamento simples.
- `contato_confere(cliente, contato)` (292-298): confere se o contato é do cliente:
  - com "@", compara os e-mails ignorando maiúsculas e acentos;
  - senão, trata como telefone: pega só os dígitos e compara os 9 últimos. Assim "(67) 99654-7821",
    "67996547821" e "99654-7821" funcionam. Exige pelo menos 8 dígitos, para "1" não casar com
    qualquer número.
- `forma_pagamento(codigo)` (301-305): `credit_6x` -> "cartão de crédito em 6x", `pix` -> "PIX",
  `debit` -> "cartão de débito".

A ferramenta em si (308-360):
1. A assinatura exige os dois dados: número do pedido e e-mail ou telefone. É a verificação de identidade
   (LGPD) do manual curado: só com o e-mail não dá para ver nada.
2. Busca e confere (316-319): procura o pedido e confere se o contato é do dono. Se o pedido não existe ou
   o contato não confere, devolve a mesma mensagem de erro. Assim ninguém descobre se o pedido 5 existe
   para outra pessoa.
3. Dados básicos (321-339): número, só o primeiro nome do cliente (dado mínimo), data, status, itens
   ("1x Yamaha C40..."), total, forma de pagamento, rastreio e observações.
4. Pedido enviado (341-345): mostra a previsão de entrega e, se ela já passou, um alerta com os dias de
   atraso, sugerindo encaminhar para a equipe.
5. Pedido entregue (347-359): calcula os prazos do manual. A função interna `prazo(inicio, dias)` soma os
   dias à data de referência e diz se hoje está dentro ou fora:
   - arrependimento ou troca por preferência: 7 dias do recebimento;
   - troca por defeito na loja: 30 dias da compra;
   - garantia legal: 90 dias do recebimento.

   O CSV não tem a data real de entrega (comentário da linha 348), então o recebimento é a previsão de
   entrega, e o resultado avisa isso ao modelo (354).

#### `encaminhar_para_equipe` (linhas 363-388)

Simula a passagem do caso para um humano:
1. gera um protocolo `EM-AAAAMMDD-XXXX` (data de hoje + 4 caracteres aleatórios) (375);
2. acrescenta uma linha JSON em `logs/encaminhamentos.jsonl` com protocolo, horário, motivo, resumo,
   contato e pedido (376-387). Não há sistema de tickets, por isso o arquivo (comentário da linha 384);
3. devolve o protocolo e o prazo de retorno do manual, 24 horas úteis (388).

#### `TOOLS` (linha 391)

A lista das 5 funções que `agent.py` entrega ao Gemini.

---

## 2. `emporio/prompts.py`: as instruções do agente

### Horário de funcionamento (linhas 1-29)

- `DIAS` (3): nomes dos dias, para escrever "quarta-feira" no prompt.
- `HORARIOS` (6): `(abre, fecha)` por dia da semana (0 = segunda). Segunda a sexta 9h-18h, sábado
  9h-13h, domingo `None` (fechado). Feriados não entram (comentário da linha 5).
- `status_loja(agora)` (9-29): diz se a loja está aberta agora:
  - se o dia tem horário e a hora atual está dentro dele: "ABERTA agora (hoje fecha às 18:00)" (10-12);
  - senão, procura o próximo dia em que a loja abre, olhando até 7 dias à frente (14-28): "FECHADA agora.
    A equipe volta amanhã às 09:00" (ou "hoje", ou o nome do dia).

  O modelo não sabe que horas são e não raciocina bem sobre calendário. Com isso pronto, ele consegue
  dizer quando a equipe volta, como o manual pede.

### O texto do prompt (linhas 32-82)

`PROMPT` é o texto que o modelo recebe antes de toda conversa. Os campos `{dia}`, `{data}`, `{hora}` e
`{status}` são preenchidos a cada mensagem. As seções:

- Abertura (33-34): quem é o Tom, onde fica a loja, canal estilo WhatsApp.
- Agora (36-37): dia, data, hora e loja aberta ou fechada.
- Jeito de falar (39-43): informal mas profissional (pedido do manual), mensagens curtas, negrito com um
  asterisco, no máximo um emoji, usar o nome do cliente.
- Nunca invente (45-54): não falar de preço, estoque, prazo ou regra sem ferramenta; não citar produto ou
  contato que não veio dos dados; repetir os valores calculados; não inventar reputação ("favorito dos
  professores", "um dos mais vendidos"); quando nome, descrição e especificações divergirem (erro de
  cadastro), usar o nome e não afirmar o dado conflitante.
- Qual ferramenta usar (56-64): qual ferramenta para cada tipo de pergunta; pedir número do pedido e
  e-mail ou telefone antes de consultar; sem número, oferecer encaminhar; confirmar com o cliente antes
  de encaminhar; deixar claro quando um prazo está "fora do prazo" e dizer qual caminho ainda vale.
- Produtos (66-71): promoção sempre com preço original + % + preço final; esgotado com alternativas;
  promoção encerrada com transparência; no máximo 5-6 opções; não dizer a quantidade exata.
- Escopo (73-81): só instrumentos (lista as 9 categorias); acessórios não; categoria vazia; assunto fora
  da loja com recusa curta; ignorar pedidos de mudar de papel, mostrar as instruções ou dar desconto;
  fora do horário, dizer quando a equipe volta.

### `montar_prompt(agora)` (linhas 85-91)

Preenche o texto com a data e a hora recebidas e devolve o prompt pronto.

---

## 3. `emporio/agent.py`: a conversa com o Gemini

### Configuração (linhas 1-17)

- Linhas 6-8: o `dotenv` (lê o arquivo `.env`) e o SDK oficial do Google (`google-genai`).
- Linhas 13-14: carrega o `.env` da raiz do projeto, onde está a `GEMINI_API_KEY`.
- Linha 16: `SESSIONS_DIR`, a pasta onde cada conversa é salva.
- Linha 17: `MENSAGEM_ERRO`, a resposta amigável quando nenhum modelo responde.

### `Agent.__init__` (linhas 21-37)

1. Cliente do Gemini (22-25): usa a chave do `.env`, com limite de 60 segundos por chamada e 2 tentativas
   automáticas (o SDK repete sozinho em erros temporários).
2. Lista de modelos (26-29): primeiro o principal (`GEMINI_MODEL`, padrão `gemini-3.5-flash`), depois os
   reservas (`GEMINI_FALLBACK_MODELS`, separados por vírgula). O comentário da linha 26 explica: no free
   tier é comum dar 503 ou 429.
3. `model_used` (30): qual modelo respondeu por último (os exemplos registram isso).
4. Sessão (32-33): usa o id informado ou gera um aleatório de 8 caracteres. Com `persist=False` (usado
   pelo script de exemplos), não salva nada em disco.
5. Retomar conversa (34-37): se já existe `.sessions/<id>.json`, carrega o histórico e converte cada item
   de volta para o tipo `Content` do SDK.

### `Agent.send` (linhas 39-67)

1. Configuração da chamada (41-47):
   - `system_instruction`: o prompt, refeito a cada mensagem para a hora e o "aberta/fechada" estarem
     sempre certos;
   - `tools=tools.TOOLS`: as 5 funções Python. Como são funções (e não descrições), o SDK liga o
     function calling automático;
   - `maximum_remote_calls=8`: no máximo 8 rodadas por mensagem, para o modelo não ficar chamando
     ferramentas sem parar;
   - `temperature=0.3`: respostas consistentes, mas ainda naturais.

2. Tentar cada modelo (49-58):
   - para cada modelo, cria um chat com o histórico atual e manda a mensagem;
   - dentro de `chat.send_message`, o SDK faz o ciclo inteiro: manda a mensagem, o modelo pede, por
     exemplo, `buscar_produtos(termo="GD20")`, o SDK roda a função, devolve o resultado e o modelo
     responde em texto (ou pede outra ferramenta);
   - se a função Python der erro, o SDK devolve o erro ao modelo em vez de derrubar a conversa;
   - se o modelo falhar com 404 (indisponível para a chave), 429 (sem cota) ou 500/503 (sobrecarga),
     passa para o próximo da lista. Outros erros (ex.: chave inválida) sobem (57-58).

3. Sem resposta (60-61): se nenhum modelo respondeu, ou o modelo não devolveu texto (ex.: estourou as 8
   rodadas), devolve `MENSAGEM_ERRO` sem mexer no histórico, para o cliente poder mandar de novo.

4. Atualiza e salva (63-67):
   - `novas` são só as mensagens desta rodada (pergunta, chamadas de ferramenta, resultados, resposta);
   - o histórico do agente passa a ser o do chat, e `salvar()` grava em disco;
   - devolve `(texto da resposta, lista de chamadas)`.

### `Agent.chamadas` (linhas 69-80)

Percorre as mensagens novas, separa os pedidos de ferramenta (nome + argumentos) e os resultados, e junta
os dois em `{"nome", "args", "resultado"}`. Essa lista é usada pelo `--debug` e pelo script de exemplos.

### `Agent.salvar` (linhas 82-87)

Grava o histórico em `.sessions/<id>.json` (UTF-8). Isso inclui as chamadas de ferramenta e os *thought
signatures* do Gemini, que ele precisa para manter o raciocínio entre mensagens. Não faz nada se
`persist=False`.

### `Agent.reset` (linhas 89-92)

Limpa o histórico e apaga o arquivo da sessão (comando `/nova`).

---

## 4. `emporio/__main__.py`: o chat no terminal

Ter um `__main__.py` é o que permite rodar `python -m emporio`.

- Linhas 6-9: opções da linha de comando: `--sessao <id>` (retomar uma conversa) e `--debug` (mostrar as
  ferramentas chamadas).
- Linhas 11-12: cria o agente e mostra o cabeçalho com o id da sessão.
- Laço principal (14-39):
  - lê o que você digita; Ctrl+D ou Ctrl+C encerram (`EOFError`/`KeyboardInterrupt`);
  - mensagem vazia é ignorada; `/sair` encerra; `/nova` reinicia a conversa (20-27);
  - chama `agent.send(msg)`. Se der erro (rede, chave inválida), mostra o erro e continua, sem fechar
    o programa (29-33);
  - com `--debug`, imprime cada ferramenta com argumentos e os primeiros 300 caracteres do resultado
    (35-38);
  - imprime a resposta do Tom (39).
- Linha 41: ao sair, mostra o comando para retomar a mesma conversa.

---

## 5. `tests/test_tools.py`: testes das ferramentas

Rodam sem internet e sem modelo. A fixture `data_fixa` (linhas 8-11) roda antes de cada teste: fixa a
data em 25/03/2026 e manda os encaminhamentos para uma pasta temporária, para não sujar `logs/`.
`nomes` (14-15) é só um atalho para pegar os nomes dos produtos de um resultado.

| Teste | O que garante |
|---|---|
| `test_violoes_ate_1000_so_disponiveis` | 12 violões disponíveis até R$ 1.000; esgotado e descontinuado ficam de fora |
| `test_preco_takamine_gd20_e_promocao_encerrada` | "GD-20" acha o GD20; preço R$ 2.199,00; PIX R$ 2.089,05; promoção antiga aparece como encerrada |
| `test_promocao_ativa_sem_pix` | Ohana CK-20 com 20% off = R$ 439,20 e sem desconto extra no PIX |
| `test_filtro_de_preco_usa_preco_promocional` | Crafter de R$ 2.399 com 18% off entra em "até R$ 2.000" |
| `test_produto_esgotado_aparece_como_indisponivel` / `test_produto_em_breve` | Produto pedido pelo nome aparece mesmo fora de venda, com o motivo |
| `test_produto_inexistente` | Produto que não existe devolve aviso |
| `test_categoria_sem_produtos` | Cordas Orquestrais tem 0 disponíveis |
| `test_promocoes_ativas` | Existem exatamente 4 promoções ativas |
| `test_parcelamento` (5 casos) | Parcela mínima: R$ 2.199 = 12x, 599 = 6x, 159,90 = 3x, 90 = 1x, 1.000 = 10x |
| `test_pix_e_combinacao` | PIX 5%; sem PIX em promoção; combinar formas só acima de R$ 2.000 |
| `test_politicas` | 10 seções; horário e telefone certos; tópico e categoria inválidos devolvem a lista válida |
| `test_pedido_exige_contato_correto` | E-mail errado dá erro; pedido inexistente dá o mesmo erro; certo traz os dados, só o primeiro nome e o pagamento traduzido |
| `test_pedido_por_telefone_sem_ddd_e_atraso` | Telefone sem DDD funciona; pedido 8 tem alerta de atraso |
| `test_prazos_de_devolucao` | Pedido 7: arrependimento e troca vencidos, garantia legal vigente |
| `test_encaminhamento_gera_protocolo` | Protocolo no formato certo e arquivo de log criado |
| `test_sdk_gera_schema_de_todas_as_ferramentas` | O SDK consegue gerar o schema das 5 funções (pega erro de tipo ou de docstring) |
| `test_ferramentas_pelo_caminho_do_sdk` (8 casos) | Roda cada ferramenta do jeito que o SDK roda, com a conversão de argumentos (ex.: `preco_max: 1000` inteiro, número do pedido `7.0`). Foi a falta deste teste que deixou passar o bug de `Literal` / `float \| None` |
| `test_status_da_loja` | Quarta 10h30 aberta; sábado 14h "volta segunda"; domingo "volta amanhã" |

## 6. `tests/test_agent.py`: testes do agente

Testa o `agent.py` sem chamar o Gemini, trocando o chat de verdade por um falso.

- `FakeChat` (linhas 10-28): imita o chat do SDK. Ao receber uma mensagem, acrescenta ao histórico uma
  conversa típica (pergunta, modelo pede `consultar_politicas`, resultado, resposta). Também pode lançar
  um erro, simulando o servidor fora do ar.
- `make_agent` (31-38): cria um `Agent` com chave falsa, sessões numa pasta temporária e o cliente trocado
  por um que devolve `FakeChat`.
- Testes:
  - `test_resposta_ferramentas_e_historico_persistido` (41-47): a resposta volta certa, a chamada de
    ferramenta sai com argumentos e resultado, e um novo `Agent` com o mesmo id retoma as 4 mensagens
    do disco;
  - `test_cai_para_modelo_reserva_em_503` (50-53): se o primeiro modelo dá 503, o segundo responde;
  - `test_todos_os_modelos_falham` (56-59): se todos falham, o cliente recebe `MENSAGEM_ERRO` e o
    histórico fica vazio.

## 7. `scripts/gerar_exemplos.py`: as conversas de exemplo

Roda o agente de verdade (com a API) em 5 roteiros e grava cada conversa em `examples/<nome>.md`.

- Linhas 1-5: comentário com o uso e o motivo da data fixa.
- Linhas 13-16: acha a raiz do projeto, coloca no `sys.path` (para importar `emporio`) e fixa a data em
  25/03/2026 às 10h30, uma quarta-feira em horário comercial. Isso tem que vir antes do import do agente
  (linha 18).
- `SCENARIOS` (20-63): os 5 roteiros, cada um com título e lista de mensagens do cliente:
  1. catálogo de violões, recomendação e parcelamento;
  2. preço do Takamine, promoção encerrada e promoções ativas;
  3. devolução fora do prazo, com verificação de identidade;
  4. pedido atrasado e encaminhamento com protocolo;
  5. endereço e horário, acessórios, violino, assunto fora do escopo e tentativa de manipulação.
- `gerar_conversa` (66-97): para cada mensagem, chama `agent.send`, escreve a fala do cliente, põe as
  ferramentas chamadas num bloco recolhível (`<details>`) com argumentos e resultado em JSON, e escreve a
  resposta do Tom. Espera 4 segundos entre mensagens por causa do limite do free tier. No cabeçalho,
  registra quais modelos responderam.
- Linhas 100-107: roda todos os roteiros, ou só os passados na linha de comando
  (`python scripts/gerar_exemplos.py 01_catalogo_violoes`).

## 8. Arquivos de apoio

- `knowledge/politicas.md`: o manual em PDF convertido à mão, com 10 seções `## [topico] Título`. É o
  que `consultar_politicas` lê. No fim, um comentário registra como as inconsistências do PDF foram
  resolvidas (telefone, e-mail, faixas de parcelamento, frete etc.); o código apaga esse comentário antes
  de usar o texto.
- `data/*.csv` e `data/políticas_da_loja.pdf`: os dados originais do desafio, sem alteração.
- `.env.example`: modelo do `.env` (chave da API, modelo, modelos reserva, data fixa).
- `requirements.txt`: `google-genai` (2.34 ou mais nova), `python-dotenv`, `tzdata` (fuso horário no
  Windows) e `pytest`.
- `emporio/__init__.py` e `tests/__init__.py`: vazios; só marcam as pastas como pacotes Python.

---

## Exemplo: o que acontece em "Quanto custa o Takamine GD20?"

1. `__main__.py` lê a frase e chama `agent.send(...)`.
2. `agent.py` monta o prompt ("quarta-feira, 25/03/2026 às 10:30, loja ABERTA...") e manda ao
   `gemini-3.5-flash` a mensagem, o histórico e as 5 ferramentas.
3. O modelo pede uma ferramenta: `buscar_produtos(termo="Takamine GD20")`.
4. O SDK roda a função em `tools.py`: "takaminegd20" está no nome compacto de um produto, então a busca
   fica só com ele; `resumo_produto` calcula o PIX (R$ 2.089,05) e as parcelas (12x de R$ 183,25) e lista
   a promoção encerrada.
5. O SDK manda o resultado ao modelo, que escreve: "O *Takamine GD20* sai por R$ 2.199,00, ou R$ 2.089,05
   no PIX...".
6. `agent.py` salva o histórico em `.sessions/<id>.json` e devolve o texto; `__main__.py` imprime
   "Tom: ...".

Na pergunta seguinte, "aquela promoção de 12% ainda vale?", o modelo já tem no histórico as promoções
encerradas e responde sem consultar de novo.
