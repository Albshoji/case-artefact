import csv
import json
import os
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"
TZ = ZoneInfo("America/Campo_Grande")


def now():
    # AGENT_TODAY / AGENT_TIME servem pra fixar a data nos exemplos e testes,
    # já que os pedidos do csv são de out/2025 a mar/2026
    agora = datetime.now(TZ)
    data = os.getenv("AGENT_TODAY")
    if data:
        agora = datetime.combine(date.fromisoformat(data), agora.time(), TZ)
    hora = os.getenv("AGENT_TIME")
    if hora:
        h, m = hora.split(":")
        agora = agora.replace(hour=int(h), minute=int(m))
    return agora


def ler_csv(nome):
    with open(ROOT / "data" / f"desafio_tecnico_ai_eng - {nome}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def compactar(texto):
    # "Takamine GD-20" -> "takaminegd20"
    return re.sub(r"[^a-z0-9]", "", normalizar(texto))


STOPWORDS = {"a", "o", "e", "de", "da", "do", "em", "um", "uma", "com", "para", "pra", "ate", "que"}
SINONIMOS = {
    "eletroacustico": "eletrico",
    "eletroacustica": "eletrico",
    "eletrica": "eletrico",
    "classico": "nylon",
    "steel": "aco",
    "sintetizador": "synth",
}


def palavras(texto):
    resultado = set()
    for p in re.findall(r"[a-z0-9]+", normalizar(texto)):
        if p in STOPWORDS:
            continue
        # singular bem simples: violoes -> violao, cordas -> corda
        if p.endswith("oes"):
            p = p[:-3] + "ao"
        elif len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        resultado.add(SINONIMOS.get(p, p))
    return resultado


# os dados são pequenos (65 produtos, 20 pedidos), então carrego tudo em memória

CATEGORIAS = {int(c["category_id"]): c["name"] for c in ler_csv("categories")}
CLIENTES = {int(c["customer_id"]): c for c in ler_csv("customers")}

PEDIDOS = {}
for pedido in ler_csv("orders"):
    pedido["itens"] = []
    PEDIDOS[int(pedido["order_id"])] = pedido
for item in ler_csv("order_items"):
    PEDIDOS[int(item["order_id"])]["itens"].append(item)

PRODUTOS = {}
for linha in ler_csv("products"):
    produto = {
        "id": int(linha["product_id"]),
        "nome": linha["name"],
        "categoria": CATEGORIAS[int(linha["category_id"])],
        "preco": float(linha["price_brl"]),
        "estoque": int(linha["stock_quantity"] or 0),
        "status": linha["status"],
        "descricao": linha["description"],
        "specs": json.loads(linha["specs"]) if linha["specs"] else {},
        "promo": None,
        "promos_encerradas": [],
    }
    specs = " ".join(f"{k} {v}" for k, v in produto["specs"].items())
    specs = specs.replace("electronics yes", "eletrico")
    produto["busca"] = palavras(f"{produto['nome']} {produto['categoria']} {produto['descricao']} {specs}")
    produto["nome_compacto"] = compactar(produto["nome"])
    PRODUTOS[produto["id"]] = produto

for linha in ler_csv("promotions"):
    produto = PRODUTOS.get(int(linha["product_id"]))
    if not produto:
        continue
    promo = {"campanha": linha["description"], "desconto": float(linha["discount_percent"])}
    if linha["is_active"] == "1":
        produto["promo"] = promo
    else:
        # guardo as antigas pro agente conseguir responder "aquela promoção ainda vale?"
        produto["promos_encerradas"].append(promo)

# manual dividido em seções "## [topico] Titulo"
manual = (ROOT / "knowledge" / "politicas.md").read_text(encoding="utf-8")
manual = re.sub(r"<!--.*?-->", "", manual, flags=re.S)
POLITICAS = {}
for topico, texto in re.findall(r"^## \[(\w+)\][^\n]*\n(.*?)(?=^## |\Z)", manual, re.M | re.S):
    POLITICAS[topico] = texto.strip()


def brl(valor):
    s = f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return "R$ " + s


def preco_final(produto):
    if produto["promo"]:
        return round(produto["preco"] * (1 - produto["promo"]["desconto"] / 100), 2)
    return produto["preco"]


def disponibilidade(produto):
    if produto["status"] == "discontinued":
        return "descontinuado (saiu do catálogo)"
    if produto["status"] == "coming_soon":
        return "em breve (ainda não está à venda)"
    if produto["estoque"] > 0:
        return "disponível"
    return "esgotado no momento"


def parcela_minima(n):
    if n == 1:
        return 0
    if n <= 3:
        return 50
    if n <= 6:
        return 80
    return 100


def max_parcelas(valor):
    maximo = 1
    for n in range(2, 13):
        if valor / n >= parcela_minima(n):
            maximo = n
    return maximo


def resumo_produto(produto):
    preco = preco_final(produto)
    parcelas = max_parcelas(preco)
    r = {
        "id": produto["id"],
        "nome": produto["nome"],
        "categoria": produto["categoria"],
        "disponibilidade": disponibilidade(produto),
        "preco_tabela": brl(produto["preco"]),
    }
    if produto["promo"]:
        promo = produto["promo"]
        r["promocao_ativa"] = f"{promo['campanha']}: {promo['desconto']:g}% de desconto, sai por {brl(preco)} (PIX não dá desconto extra)"
    else:
        r["preco_no_pix"] = brl(round(preco * 0.95, 2))
    r["cartao"] = f"até {parcelas}x de {brl(preco / parcelas)} sem juros"
    if produto["promos_encerradas"]:
        r["promocoes_encerradas"] = [f"{p['campanha']} ({p['desconto']:g}%)" for p in produto["promos_encerradas"]]
    if produto["status"] == "active" and 0 < produto["estoque"] <= 2:
        r["estoque"] = "últimas unidades"
    r["descricao"] = produto["descricao"]
    r["especificacoes"] = produto["specs"]
    return r


# Ferramentas do agente. O SDK do Gemini monta o schema a partir da assinatura e da docstring.
# Uso só str/float/int/bool nos parâmetros porque o SDK não converte Literal nem "float | None"
# (a chamada quebrava), por isso as opções válidas estão escritas na docstring.

def buscar_produtos(termo: str = "", categoria: str = "", preco_max: float = 0, so_promocoes: bool = False) -> dict:
    """Busca instrumentos no catálogo. Serve pra qualquer pergunta de produto, preço, estoque ou
    promoção: um modelo específico ("quanto custa o Takamine GD20?"), uma busca aberta ("violões até
    R$ 1000") ou "tem algo em promoção?" (so_promocoes=true).

    Args:
        termo: marca, modelo ou característica (ex.: "Yamaha", "GD20", "nylon", "7 cordas").
        categoria: uma destas: Guitarras, Baixos, Baterias e Percussão, Teclados e Pianos, Violões,
            Instrumentos de Sopro (Madeiras), Instrumentos de Sopro (Metais), Cordas Orquestrais, Ukuleles.
        preco_max: preço máximo em reais, 0 para sem limite. Considera o preço promocional, sem o desconto do PIX.
        so_promocoes: só produtos com promoção ativa.

    Retorna os produtos disponíveis (até 10, do mais barato ao mais caro) e, quando tem termo, também
    os que batem com a busca mas não estão à venda (esgotado, descontinuado ou em breve).
    """
    if categoria and categoria not in CATEGORIAS.values():
        return {"erro": f"Categoria inválida: {categoria}", "categorias_validas": list(CATEGORIAS.values())}

    encontrados = []
    for p in PRODUTOS.values():
        if categoria and p["categoria"] != categoria:
            continue
        if preco_max and preco_final(p) > preco_max:
            continue
        if so_promocoes and not p["promo"]:
            continue
        encontrados.append(p)

    termos = palavras(termo)
    if termos:
        busca = compactar(termo)
        pelo_nome = [p for p in encontrados if len(busca) >= 4 and busca in p["nome_compacto"]]
        if pelo_nome:
            encontrados = pelo_nome
        else:
            # fica com quem bate com mais palavras da busca
            acertos = {}
            for p in encontrados:
                acertos[p["id"]] = sum(1 for t in termos if t in p["busca"] or t in p["nome_compacto"])
            melhor = max(acertos.values(), default=0)
            encontrados = [p for p in encontrados if melhor > 0 and acertos[p["id"]] == melhor]

    encontrados.sort(key=preco_final)
    disponiveis = [p for p in encontrados if disponibilidade(p) == "disponível"]
    resultado = {
        "total_disponiveis": len(disponiveis),
        "disponiveis": [resumo_produto(p) for p in disponiveis[:10]],
    }
    if termos:
        indisponiveis = [p for p in encontrados if p not in disponiveis]
        resultado["indisponiveis"] = [resumo_produto(p) for p in indisponiveis[:5]]
    if not encontrados:
        resultado["aviso"] = "Nenhum produto encontrado com esses filtros."
    return resultado


def calcular_pagamento(valor: float, preco_promocional: bool = False) -> dict:
    """Calcula PIX e parcelas no cartão para um valor total, por exemplo a soma de vários produtos.
    Pra um produto só não precisa: buscar_produtos já traz PIX e parcelas.

    Args:
        valor: valor total em reais.
        preco_promocional: true se o valor já está com desconto de promoção (aí o PIX não dá os 5%).
    """
    parcelas = max_parcelas(valor)
    if preco_promocional:
        pix = brl(valor) + " (sem desconto, preço promocional)"
    else:
        pix = brl(round(valor * 0.95, 2))
    return {
        "valor": brl(valor),
        "pix": pix,
        "cartao": f"até {parcelas}x de {brl(valor / parcelas)} sem juros",
        "debito_ou_boleto": brl(valor),
        "pode_combinar_formas": valor > 2000,
    }


def consultar_politicas(topico: str) -> dict:
    """Lê uma seção do manual da loja. Consultar antes de responder sobre endereço, contato, horário,
    formas de pagamento, trocas e devoluções, frete e prazo de entrega, rastreio, regras de promoção,
    atendimento (acessórios, reclamações), garantia ou privacidade.

    Args:
        topico: um destes: sobre_loja, horario, pagamento, trocas_devolucoes, frete_entrega,
            rastreamento, promocoes, atendimento, garantia, privacidade.
    """
    if topico not in POLITICAS:
        return {"erro": f"Tópico inválido: {topico}", "topicos_validos": list(POLITICAS)}
    return {"topico": topico, "texto": POLITICAS[topico]}


STATUS = {
    "pending": "Pendente: aguardando confirmação do pagamento",
    "confirmed": "Confirmado: pagamento aprovado, em separação",
    "shipped": "Enviado: a caminho do endereço de entrega",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

PAGAMENTOS = {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto"}


def contato_confere(cliente, contato):
    if "@" in contato:
        return normalizar(contato.strip()) == normalizar(cliente["email"])
    # telefone: comparo só os últimos 9 dígitos, assim funciona com ou sem DDD
    digitos = re.sub(r"\D", "", contato)
    telefone = re.sub(r"\D", "", cliente["phone"])
    return len(digitos) >= 8 and telefone.endswith(digitos[-9:])


def forma_pagamento(codigo):
    if codigo.startswith("credit_"):
        vezes = codigo.replace("credit_", "").replace("x", "")
        return f"cartão de crédito em {vezes}x"
    return PAGAMENTOS.get(codigo, codigo)


def consultar_pedido(numero_pedido: int, contato: str) -> dict:
    """Status, itens, rastreio e prazos de devolução, troca e garantia (já calculados) de um pedido.
    Precisa do número do pedido E do e-mail ou telefone cadastrado: peça os dois ao cliente antes.

    Args:
        numero_pedido: número do pedido.
        contato: e-mail ou telefone informado pelo cliente.
    """
    pedido = PEDIDOS.get(int(numero_pedido))
    # mesma resposta se o pedido não existe ou se é de outra pessoa
    if not pedido or not contato_confere(CLIENTES[int(pedido["customer_id"])], contato):
        return {"erro": "Não encontrei pedido com esses dados. Confira o número e o e-mail/telefone da compra."}

    hoje = now().date()
    compra = date.fromisoformat(pedido["order_date"])
    previsao = None
    if pedido["estimated_delivery"]:
        previsao = date.fromisoformat(pedido["estimated_delivery"])

    cliente = CLIENTES[int(pedido["customer_id"])]
    itens = [f"{i['quantity']}x {PRODUTOS[int(i['product_id'])]['nome']}" for i in pedido["itens"]]
    r = {
        "numero": numero_pedido,
        "cliente": cliente["name"].split()[0],
        "data_compra": compra.isoformat(),
        "status": STATUS[pedido["status"]],
        "itens": itens,
        "total": brl(float(pedido["total_brl"])),
        "pagamento": forma_pagamento(pedido["payment_method"]),
        "rastreio": pedido["tracking_code"] or None,
        "observacoes": pedido["notes"] or None,
    }

    if pedido["status"] == "shipped" and previsao:
        r["previsao_entrega"] = previsao.isoformat()
        if previsao < hoje:
            atraso = (hoje - previsao).days
            r["alerta"] = f"Previsão de entrega vencida há {atraso} dias: ofereça encaminhar para a equipe."

    if pedido["status"] == "delivered" and previsao:
        # o csv não tem a data real de entrega, uso a previsão
        def prazo(inicio, dias):
            fim = inicio + timedelta(days=dias)
            situacao = "dentro do prazo" if hoje <= fim else "fora do prazo"
            return f"até {fim:%d/%m/%Y} ({situacao})"

        r["recebido_em"] = f"{previsao.isoformat()} (previsão de entrega; o sistema não registra a data real)"
        r["prazos"] = {
            "arrependimento_ou_troca_por_preferencia (7 dias do recebimento)": prazo(previsao, 7),
            "troca_por_defeito_na_loja (30 dias da compra)": prazo(compra, 30),
            "garantia_legal (90 dias do recebimento)": prazo(previsao, 90),
        }
    return r


def encaminhar_para_equipe(motivo: str, resumo: str, contato_cliente: str = "", numero_pedido: int = 0) -> dict:
    """Registra o caso pra equipe humana e gera um protocolo. Usar em reclamação, devolução, troca,
    cancelamento, atraso, cotação de frete pra outra cidade ou quando o cliente pedir um humano.
    Confirme com o cliente antes de registrar.

    Args:
        motivo: reclamacao, devolucao_ou_troca, cancelamento, atraso_entrega, cotacao_frete, garantia,
            atendimento_humano ou outro.
        resumo: resumo do caso para a equipe.
        contato_cliente: e-mail ou telefone do cliente.
        numero_pedido: número do pedido, 0 se não tiver.
    """
    protocolo = f"EM-{now():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    registro = {
        "protocolo": protocolo,
        "em": now().isoformat(),
        "motivo": motivo,
        "resumo": resumo,
        "contato": contato_cliente,
        "pedido": numero_pedido or None,
    }
    # não tem sistema de tickets, então só salvo num arquivo
    LOGS_DIR.mkdir(exist_ok=True)
    with open(LOGS_DIR / "encaminhamentos.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {"protocolo": protocolo, "prazo_retorno": "até 24 horas úteis"}


TOOLS = [buscar_produtos, calcular_pagamento, consultar_politicas, consultar_pedido, encaminhar_para_equipe]
