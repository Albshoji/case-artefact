# Tom, atendente virtual da Empório da Música

Protótipo de um agente de atendimento por texto para a Empório da Música, uma loja (fictícia) de
instrumentos musicais em Campo Grande/MS. O Tom responde as dúvidas mais comuns dos clientes: catálogo,
preço, promoção, status de pedido, troca e devolução, horário, pagamento e frete. Ele decide sozinho
quando precisa olhar os dados (CSVs) e quando precisa olhar as políticas da loja (o manual em PDF).

Em resumo: Python, Gemini 3.5 Flash pelo free tier do Google AI Studio, 5 ferramentas chamadas pelo
function calling automático do SDK e um chat no terminal que guarda o histórico. As conversas de exemplo
estão em [`examples/`](examples/).

## Como rodar

Precisa de Python 3.10+ e de uma chave gratuita da API do Gemini
([Google AI Studio, "Get API key"](https://aistudio.google.com/apikey)).

```bash
git clone https://github.com/Albshoji/case-artefact.git
cd case-artefact

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # e coloque a GEMINI_API_KEY no .env
```

Para conversar:

```bash
python -m emporio                  # conversa nova
python -m emporio --debug          # mostra as ferramentas chamadas e o que voltou
python -m emporio --sessao maria   # cria ou retoma a conversa "maria" (fica salva em .sessions/)
```

Dentro do chat, `/nova` reinicia a conversa e `/sair` fecha.

Variáveis do `.env`:

- `GEMINI_API_KEY` (obrigatória): chave do Google AI Studio.
- `GEMINI_MODEL`: modelo principal. Padrão `gemini-3.5-flash`.
- `GEMINI_FALLBACK_MODELS`: modelos reserva, separados por vírgula, usados quando o principal dá
  503 ou 429. Padrão `gemini-3-flash-preview,gemini-3.6-flash`.
- `AGENT_TODAY`: fixa a data de hoje do agente (`AAAA-MM-DD`). Os pedidos do CSV são de out/2025 a
  mar/2026, então com `AGENT_TODAY=2026-03-25` os status e prazos fazem sentido.
- `AGENT_TIME`: fixa a hora (`HH:MM`), útil para testar o agente com a loja fechada.

Testes e exemplos:

```bash
pytest                             # 33 testes, sem rede
python scripts/gerar_exemplos.py   # gera de novo examples/*.md rodando o agente de verdade
```

## Como funciona

```
cliente -> __main__.py (terminal) -> Agent.send() em agent.py
                                       histórico + prompt com data e hora
                                       |
                                       v
                                     Gemini (SDK google-genai)
                                     chama as ferramentas sozinho, até 8 rodadas por mensagem
                                       |
                                       v
                                     tools.py: CSVs + knowledge/politicas.md
                                     (preço, PIX, parcelas, prazos, verificação de identidade)
```

São 4 arquivos de código em `emporio/`:

- `tools.py`: carrega os CSVs e o manual, tem as regras de negócio e as 5 ferramentas;
- `prompts.py`: persona, regras e o contexto de data e hora (se a loja está aberta ou fechada);
- `agent.py`: chamada ao Gemini, troca para o modelo reserva e histórico salvo em JSON;
- `__main__.py`: o chat no terminal.

As ferramentas:

- `buscar_produtos`: qualquer pergunta de produto (um modelo específico, busca por categoria e preço
  máximo, o que está em promoção). Já devolve preço, promoção ativa ou encerrada, PIX, parcelas,
  disponibilidade e especificações.
- `calcular_pagamento`: PIX e parcelas de um total com vários produtos.
- `consultar_politicas`: lê uma seção do manual (endereço, horário, pagamento, trocas, frete, rastreio,
  promoções, atendimento, garantia, privacidade).
- `consultar_pedido`: status, itens, rastreio e os prazos de devolução, troca e garantia já calculados.
  Só funciona com o número do pedido e o e-mail ou telefone do cliente.
- `encaminhar_para_equipe`: registra reclamação, devolução, atraso, cotação de frete ou pedido de falar
  com alguém, e gera um protocolo.

As ferramentas são funções Python normais. O SDK do Gemini monta a descrição que o modelo recebe a partir
da assinatura e da docstring, então não escrevi nenhum schema à mão. Os parâmetros só usam `str`, `float`,
`int` e `bool` porque o SDK não converte argumentos para `Literal` nem para `float | None` (isso quebrou
as ferramentas, conto mais abaixo). As opções válidas ficam na docstring, e se o modelo mandar um valor
inválido a ferramenta devolve a lista certa.

## Decisões técnicas

### Function calling com ferramentas em Python

O ponto principal do desafio é o agente saber quando consultar os dados e quando consultar as políticas.
Com function calling isso fica explícito: toda consulta aparece como uma chamada com nome e argumentos, e
dá para ver isso nos exemplos (os blocos "chamadas de ferramenta").

Pensei em RAG com busca vetorial para o manual, mas ele tem uns 3 mil tokens e 10 seções bem separadas.
Chunking, embeddings e banco vetorial seriam infraestrutura a mais, com o risco de cortar uma regra no meio
(a tabela de parcelamento longe das exceções, por exemplo). Preferi converter o PDF para um markdown
revisado (`knowledge/politicas.md`) e deixar o modelo escolher o tópico. Ele recebe a seção inteira. Se o
manual crescer muito, dá para trocar o que está por trás de `consultar_politicas` por uma busca híbrida
sem mexer no resto.

Também descartei um agente que gera SQL. Seria mais flexível, mas o modelo teria que lidar com o esquema
cru (`coming_soon`, `is_active=0`, `credit_6x`) e com as regras de negócio por conta própria: aplicar a
promoção mas não somar o desconto do PIX, contar 7 dias do recebimento e 30 da compra etc. E ainda
abriria espaço para mostrar dados de outros clientes. Com ferramentas, as regras ficam em Python, com
testes, e o modelo só decide o que consultar e como falar com o cliente.

Toda conta é feita no código: preço promocional, PIX, parcelamento com parcela mínima, prazos em dias.
Modelo de linguagem erra conta e data, e num atendimento isso vira informação errada de preço, que o
próprio manual pede para evitar.

Não usei framework de agentes (LangChain, LangGraph etc.). O function calling automático do SDK do Gemini
já faz o ciclo de pedir a ferramenta, rodar a função e responder, limita o número de rodadas e devolve o
erro de uma ferramenta para o modelo sem derrubar a conversa. Para um agente só, com 5 ferramentas, um
framework seria só mais dependência.

Mantive poucas ferramentas. Uma só cobre o catálogo inteiro. Frete não tem ferramenta porque a regra
(grátis acima de R$ 500 em Campo Grande, cotação nas outras cidades) está no manual e não tem conta.

### Modelo: Gemini 3.5 Flash

Comecei com o `gemini-2.5-flash`, mas a API recusa esse modelo para chaves novas. Testei os flash
disponíveis e fiquei com o `gemini-3.5-flash`, que estava estável e rápido (uns 4 s por resposta),
enquanto o `3.7-flash` e o `3.8-flash` davam 503 por excesso de demanda.

No free tier, 503 e falta de cota (20 requisições por dia por modelo) acontecem com frequência. O SDK
tenta de novo uma vez; se continuar falhando, o agente passa para o próximo modelo de
`GEMINI_FALLBACK_MODELS`. O timeout é de 60 s.

Um modelo flash dá conta porque a parte difícil (regras, contas, busca) está nas ferramentas. O modelo
escolhe a ferramenta e escreve a resposta. Uso `temperature=0.3` para as respostas saírem consistentes
sem ficarem robóticas. Dá para trocar o modelo pelo `GEMINI_MODEL`.

### Prompt

O prompt fica em `emporio/prompts.py` e tem estas partes:

1. Persona: o Tom fala do jeito que o manual pede, "informal mas profissional, como um amigo que entende
   de música", com mensagens curtas de chat.
2. Nunca inventar: não falar de preço, estoque, prazo ou regra sem consultar uma ferramenta, não citar
   produto que não veio dos dados, repetir os valores calculados em vez de refazer a conta.
3. Qual ferramenta usar para cada tipo de pergunta.
4. Regras de comunicação do manual: promoção sempre com preço original e porcentagem, sugerir alternativa
   para produto esgotado, ser transparente sobre promoção que acabou, não dizer a quantidade exata em
   estoque.
5. Escopo: só instrumentos. Acessórios são redirecionados, e assunto que não tem a ver com a loja recebe
   uma recusa curta.
6. Segurança: ignorar pedidos para mudar de papel, mostrar as instruções ou dar desconto.
7. Data, hora e se a loja está aberta ou fechada. Isso é calculado em Python a cada mensagem, para o
   agente saber dizer quando a equipe volta.

### Interface no terminal

O foco do desafio é o agente, então fiz só um chat no terminal. A opção `--debug` mostra cada ferramenta
chamada e o que ela devolveu. O `Agent` não depende do terminal: para colocar numa API (FastAPI) ou num
webhook de WhatsApp, basta chamar `Agent.send()`.

### Histórico

Atendimento é uma conversa com várias mensagens ("é o pedido 7" só faz sentido depois da pergunta
anterior), e o cliente pode voltar depois. Por isso cada conversa fica salva em `.sessions/<id>.json`, com
as chamadas de ferramenta e os *thought signatures* do Gemini, que ele usa para manter o raciocínio entre
mensagens. `--sessao <id>` retoma a conversa; num canal real o id seria o telefone do cliente. O histórico
só muda quando a resposta chega, então se a API falhar o cliente pode mandar de novo.

### Privacidade (LGPD)

`consultar_pedido` só devolve dados se o número do pedido e o e-mail ou telefone baterem com o cadastro.
A mensagem de erro é igual para "pedido não existe" e "contato não confere", assim ninguém descobre se um
pedido de outra pessoa existe. O agente só recebe o primeiro nome do cliente.

## Dados e suposições

### CSVs

- `specs` é um JSON dentro do CSV, com chaves diferentes por categoria (violão tem `top` e `strings`,
  bateria tem `shells`...). Converto para dicionário e uso na busca, trocando `steel` por aço e
  `electronics: yes` por elétrico.
- Disponibilidade vem de `status` + estoque: ativo com estoque está disponível; ativo sem estoque está
  esgotado (e o agente procura alternativa na mesma categoria); `discontinued` saiu do catálogo, mesmo
  com estoque (o Ibanez Bass 2X tem 13 unidades); `coming_soon` ainda não está à venda.
- Há várias promoções por produto, quase todas inativas. Só as com `is_active=1` mudam o preço (são 4
  produtos). As inativas ficam guardadas para o agente responder "aquela promoção ainda vale?".
- O filtro "até R$ X" usa o preço com promoção, sem o desconto do PIX.
- Os pedidos não têm a data real de entrega. Para pedido entregue, considero `estimated_delivery` como
  data de recebimento, e o agente é avisado disso.
- Telefones vêm em formatos diferentes, então comparo só os últimos dígitos (funciona com ou sem DDD).
- As categorias 6, 7 e 8 (sopros e cordas orquestrais) não têm nenhum produto. O agente diz que não tem
  no momento, em vez de dizer que a loja não vende.
- Para a busca aceitar acento, plural e modelo escrito de outro jeito, normalizo o texto (sem acento,
  minúsculo, singular simples) e comparo os nomes sem espaço nem pontuação (`GD-20` = `GD20`).

Algumas inconsistências eu encontrei e deixei como estão. Nesses casos o agente mostra o que está no
sistema:

- Os pedidos 3 e 14 têm o produto 130 (Kala KA-ABP-CTG), que está como `coming_soon`.
- O total de dois pedidos não bate com os preços atuais: pedido 3 (R$ 3.450 contra 2 × R$ 1.749) e pedido
  20 (R$ 1.400 contra R$ 799 + R$ 689). Pode ser desconto da época ou erro de cadastro. O agente informa o
  total registrado.
- Os produtos 135 a 144 (baixos, baterias e teclados) têm nome, descrição e especificação que não batem.
  O "Yamaha Bass 3X" é descrito como "contrabaixo de 5 cordas Ibanez", mas a especificação diz 4 cordas;
  a "Bateria Acústica Yamaha Kit 1" é descrita como "Pearl Export"; o "Teclado Korg Synth 1" é descrito
  como "Roland com 88 teclas", mas a especificação diz 61. O prompt manda usar o nome do produto e não
  afirmar o dado que conflita. Um efeito disso: buscar "teclado Yamaha" pode trazer o "Roland Synth 3",
  porque a descrição dele cita Yamaha.
- Os pedidos 9, 16 e 18 não respeitam a parcela mínima do manual (o 9 é R$ 349,90 em 6x, R$ 58,32 por
  parcela, abaixo dos R$ 80). Provavelmente são de antes da regra atual. O agente informa a forma de
  pagamento registrada.
- Dois clientes usam o mesmo e-mail, `bruno.martins@jmail.com` (ids 11 e 43). Como a consulta pede
  também o número do pedido, um não vê o pedido do outro.

### Manual de políticas

Converti o PDF à mão para `knowledge/politicas.md`, revisei e dividi em 10 tópicos. Algumas coisas não
batiam no PDF; anotei as decisões no próprio arquivo:

1. Telefone: a capa e a tabela de dados da empresa dizem (67) 3341-4444, e a seção 7 diz
   (67) 3321-4500. Fiquei com o (67) 3341-4444, que aparece duas vezes, inclusive na tabela oficial.
2. E-mail: a seção 1.2 traz `contato@empóriodamusica.com.br`, com acento, e a capa traz sem. Fiquei com
   a versão sem acento, que parece a certa.
3. Parcelamento: a tabela diz "parcela mínima R$ 100" no crédito, mas a seção 3.1 detalha faixas. Usei as
   faixas da 3.1, que são mais específicas: 2x a 3x com mínimo de R$ 50 (minha leitura de "sem valor
   mínimo (exceto abaixo de R$ 50,00)"), 4x a 6x com R$ 80 e 7x a 12x com R$ 100.

### Outras suposições

- Os dados são um retrato de março de 2026, então os exemplos usam `AGENT_TODAY=2026-03-25` (quarta,
  10:30). Sem a variável, o agente usa a data real.
- Considerei "região metropolitana de Campo Grande" como a cidade de Campo Grande, porque o manual não
  lista os municípios. Para as outras cidades o frete é sob cotação, já que não tenho a tabela das
  transportadoras.
- Não considero feriados para saber se a loja está aberta.
- O manual pede para indicar lojas parceiras de acessórios "quando possível", mas não diz quais são.
  O agente sugere uma loja especializada de forma genérica, sem inventar nome.
- Não existe sistema de tickets, então os encaminhamentos são gravados em `logs/encaminhamentos.jsonl`
  com um protocolo.
- O agente atende o cliente final, não a equipe, seguindo o fluxo da seção 7.2 do manual.

## Exemplos

Conversas reais geradas com `scripts/gerar_exemplos.py`. As chamadas de ferramenta aparecem em blocos
que abrem com um clique.

1. [01_catalogo_violoes](examples/01_catalogo_violoes.md): violões disponíveis até R$ 1.000, recomendação
   para iniciante, parcelas e PIX.
2. [02_preco_e_promocao_encerrada](examples/02_preco_e_promocao_encerrada.md): preço do Takamine GD20, o
   cliente fala de uma promoção que já acabou, e depois pergunta o que está em promoção.
3. [03_devolucao_arrependimento](examples/03_devolucao_arrependimento.md) (não trivial): o cliente se
   arrependeu da compra, o agente confere a identidade, vê que o prazo de 7 dias já passou e explica que
   a garantia legal ainda vale.
4. [04_pedido_atrasado_encaminhamento](examples/04_pedido_atrasado_encaminhamento.md) (não trivial):
   pedido enviado com a previsão de entrega vencida, o agente pede desculpas e registra um protocolo para
   a equipe.
5. [05_institucional_e_fora_de_escopo](examples/05_institucional_e_fora_de_escopo.md): endereço e
   horário, acessórios (a loja não vende), violino (sem estoque), uma pergunta que não tem nada a ver com
   a loja e uma tentativa de manipular o agente.

### O que vi revisando as conversas

Os exemplos foram gerados com o `gemini-3.5-flash-lite`. No dia, a cota dos modelos principais tinha
acabado e o `3.7-flash` e o `3.8-flash` davam 503, então foi a troca automática de modelo que permitiu
gerar as conversas. Conferi todos os valores citados com os CSVs (preço, PIX, parcelas, porcentagem de
promoção, datas de prazo, dias de atraso) e todos batem, porque vêm prontos das ferramentas.

O que não ficou bom:

- No exemplo 01, o modelo diz que o Yamaha C40 é "um dos modelos mais procurados por estudantes". A
  descrição dele só diz "ideal para estudantes e iniciantes" (quem tem "um dos modelos mais vendidos" na
  descrição é o Yamaha F310). O prompt proíbe esse tipo de opinião, mas o modelo lite ainda escorrega. Uma
  versão anterior, com o `gemini-3.5-flash`, chegou a dizer que o C40 era "favorito dos professores".
- Também no 01, para iniciante com nylon o agente cita 3 violões, mas a busca trouxe também o Giannini
  GN-15 (R$ 689) e o Yamaha C70 (R$ 849). Não está errado, só deixa opções de fora.
- No 03, sobre defeito, o agente diz que "a gente faz a troca na loja em até 30 dias da compra" sem
  deixar claro que esse prazo já tinha passado para o pedido 7 (a ferramenta tinha dito "fora do prazo").
  A garantia legal, até 18/05/2026, saiu certa. Depois disso coloquei no prompt uma regra para deixar
  claro quando um prazo venceu; os exemplos não foram gerados de novo depois dessa mudança.
- No 02, o agente chamou `buscar_produtos` duas vezes com os mesmos argumentos.
- Às vezes usa negrito com dois asteriscos, mesmo o prompt pedindo um.

O que funcionou: pediu o número do pedido e o contato antes de consultar (03 e 04), não prometeu a
promoção que acabou (02), recusou acessórios, o assunto fora da loja e a tentativa de manipulação (05), e
só registrou o protocolo depois que o cliente concordou (04).

## Limitações e próximos passos

Limitações:

- A qualidade das respostas foi avaliada lendo os exemplos. Os testes automáticos cobrem as ferramentas e
  o agente com um chat falso, não o comportamento do modelo.
- O free tier do Gemini tem pouca cota (20 requisições por dia por modelo, e uma mensagem pode gastar 2 ou
  3 por causa das ferramentas). A troca de modelo ajuda, mas para uso real precisaria de um plano pago.
- A busca é por palavra-chave, não semântica. "Violão bom pra igreja" não vira um tipo de instrumento. O
  modelo costuma compensar reescrevendo a busca, mas nem sempre.
- Não calcula frete por CEP e não conhece feriados.
- O encaminhamento é simulado, num arquivo JSONL.
- Os dados ficam em memória: se mudar os CSVs, precisa reiniciar o agente.
- Os exemplos foram gerados com um modelo mais fraco que o padrão, por falta de cota no dia. Com o
  `gemini-3.5-flash` a escrita tende a ser melhor.
- Num WhatsApp de verdade o telefone de quem manda a mensagem já identificaria o cliente. Aqui ele precisa
  digitar o e-mail ou telefone.

Com mais tempo, eu faria:

1. Uma bateria de avaliação do agente com umas 50 perguntas e respostas esperadas, checando se ele escolheu
   a ferramenta certa, se todo preço citado veio de uma ferramenta, se recusou o que está fora do escopo e
   se resistiu a prompt injection. Rodaria a cada mudança de prompt ou de modelo.
2. Uma checagem na saída: todo valor em R$ da resposta tem que aparecer no retorno de alguma ferramenta
   daquela mensagem; se não aparecer, gera de novo.
3. Integração com o WhatsApp (Cloud API) via FastAPI e webhook, com a sessão pelo telefone e Redis ou
   Postgres no lugar dos JSONs.
4. Postgres no lugar dos CSVs e busca semântica ou híbrida no catálogo.
5. Encaminhamento de verdade: abrir um ticket no sistema da equipe e avisar o cliente quando houver
   resposta.
6. Observabilidade: rastrear as chamadas (Langfuse ou OpenTelemetry), custo e latência por conversa.
7. Um painel para a equipe com as conversas encaminhadas e as perguntas que o agente não soube responder,
   para melhorar as políticas e o catálogo.

## Uso de assistentes de código

Usei o Claude Code (CLI da Anthropic, modelo Claude Opus 5.5) como par de programação do começo ao fim.
A divisão foi: eu defini o problema, tomei as decisões e conferi os resultados; o assistente leu os
materiais, escreveu a maior parte do código e da documentação e rodou testes e conversas para eu revisar.

Como trabalhei:

1. Análise antes do código. Pedi para o assistente ler o enunciado, o manual e os CSVs e listar o que não
   batia (produto `coming_soon` em pedido, totais divergentes, telefone e e-mail diferentes no manual,
   regras de parcelamento em conflito). As decisões sobre cada caso foram minhas e estão neste README.
2. Arquitetura discutida, não aceita pronta. Comparamos function calling, RAG e text-to-SQL, e eu escolhi
   function calling com as regras em Python e o Gemini pelo free tier, pelos motivos da seção de decisões.
3. Implementação em etapas, com um commit por etapa: dados, ferramentas com testes, prompt e agente,
   terminal, exemplos e README.
4. Nada de confiar na resposta do modelo sem conferir. Rodei conversas reais, conferi cada preço, parcela
   e prazo citado contra os CSVs, e ajustei prompt e ferramentas quando algo não estava bom (a seção
   "O que vi revisando as conversas" mostra o que ainda não está perfeito).
5. Simplificar depois de funcionar. Com a primeira versão pronta, pedi a solução mais simples possível
   sem perder precisão. O laço de function calling escrito à mão virou o automático do SDK, as
   ferramentas foram de 9 para 5 e o código do agente caiu de umas 1.280 para umas 600 linhas. Para não
   perder qualidade, comparei a busca antiga e a nova em 15 consultas típicas. A primeira tentativa perdia
   produtos (sinônimos como "eletroacústico" e "clássico"), e só segui depois de corrigir.
6. Revisão completa no final. Relemos enunciado, manual e dados linha a linha. Apareceram inconsistências
   que tinham passado (produtos 135 a 144, parcelas dos pedidos 9, 16 e 18, e-mail repetido) e uma falha de
   privacidade: dava para listar os pedidos de um cliente só com o e-mail. Agora a consulta exige o número
   do pedido e o contato.
7. Um bug que os testes não pegaram. Ao gerar os exemplos de novo, três ferramentas falhavam quando o
   modelo chamava, porque o SDK não converte argumentos para `Literal` nem um inteiro para `float | None`.
   Os testes chamavam as funções direto, então passavam. Troquei para tipos simples e criei testes que
   rodam cada ferramenta pelo mesmo caminho do SDK. A lição: com código gerado por IA, testar a integração
   real e não só as funções isoladas.
8. Legibilidade. Por fim, pedi para reescrever o código num estilo mais direto (nomes em português, menos
   comentários, laços simples), sem mudar o comportamento; os testes garantiram isso.

O que funcionou bem: o assistente acelerou muito a leitura dos materiais, a escrita e os testes. O que
exigiu atenção: ele às vezes entrega algo que parece certo e não está (o bug do SDK, a busca que perdia
produtos), então toda mudança passou por teste, comparação com os dados ou leitura das conversas antes de
entrar.

## Estrutura do repositório

```
data/                      dados do desafio (CSVs e manual em PDF)
knowledge/politicas.md     manual convertido e revisado, por tópico
emporio/                   código do agente (__main__.py, agent.py, prompts.py, tools.py)
examples/                  conversas de exemplo geradas pelo agente
scripts/gerar_exemplos.py
tests/                     pytest, sem rede
requirements.txt, .env.example
```
