"""Dados da loja (CSVs + manual) e as ferramentas que o agente pode chamar.

O LLM decide QUANDO consultar e COMO responder. Contas e regras (preço promocional, PIX,
parcelas, prazos de devolução, verificação de identidade) ficam aqui, em Python.
O SDK do Gemini gera o schema de cada ferramenta a partir da assinatura e da docstring.
"""

from __future__ import annotations

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


def now() -> datetime:
    """Data/hora do agente. AGENT_TODAY=YYYY-MM-DD e AGENT_TIME=HH:MM fixam valores (exemplos/testes)."""
    n = datetime.now(TZ)
    if d := os.getenv("AGENT_TODAY"):
        n = datetime.combine(date.fromisoformat(d), n.time(), TZ)
    if t := os.getenv("AGENT_TIME"):
        hh, mm = map(int, t.split(":"))
        n = n.replace(hour=hh, minute=mm)
    return n


# ----------------------------------------------------------------------------- carga dos dados

def _csv(name: str) -> list[dict]:
    with open(ROOT / "data" / f"desafio_tecnico_ai_eng - {name}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _norm(text: str) -> str:
    """minúsculas e sem acento."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


STOPWORDS = {"a", "o", "e", "de", "da", "do", "em", "um", "uma", "com", "para", "pra", "ate", "que"}
# como o cliente fala → como está nos dados
SYNONYMS = {"eletroacustico": "eletrico", "eletroacustica": "eletrico", "eletrica": "eletrico",
            "classico": "nylon", "steel": "aco", "sintetizador": "synth"}


def _words(text: str) -> set[str]:
    """palavras normalizadas no singular simples (violões → violao, cordas → corda)."""
    out = set()
    for w in re.findall(r"[a-z0-9]+", _norm(text)):
        if w in STOPWORDS:
            continue
        if w.endswith("oes"):
            w = w[:-3] + "ao"
        elif len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        out.add(SYNONYMS.get(w, w))
    return out


CATEGORIES = {int(r["category_id"]): r["name"] for r in _csv("categories")}
CUSTOMERS = {int(r["customer_id"]): r for r in _csv("customers")}
ORDERS = {int(r["order_id"]): r for r in _csv("orders")}
for _o in ORDERS.values():
    _o["items"] = []
for _r in _csv("order_items"):
    ORDERS[int(_r["order_id"])]["items"].append(_r)

PRODUCTS: dict[int, dict] = {}
for _r in _csv("products"):
    p = {
        "id": int(_r["product_id"]),
        "nome": _r["name"],
        "categoria": CATEGORIES[int(_r["category_id"])],
        "preco": float(_r["price_brl"]),
        "estoque": int(_r["stock_quantity"] or 0),
        "status": _r["status"],
        "descricao": _r["description"],
        "specs": json.loads(_r["specs"]) if _r["specs"] else {},
        "promo": None,               # promoção ativa
        "promos_encerradas": [],
    }
    specs = " ".join(f"{k} {v}" for k, v in p["specs"].items()).replace("electronics yes", "eletrico")
    p["busca"] = _words(f"{p['nome']} {p['categoria']} {p['descricao']} {specs}")
    p["nome_compacto"] = re.sub(r"[^a-z0-9]", "", _norm(p["nome"]))
    PRODUCTS[p["id"]] = p

for _r in _csv("promotions"):
    p = PRODUCTS.get(int(_r["product_id"]))
    if p:
        promo = {"campanha": _r["description"], "desconto": float(_r["discount_percent"])}
        if _r["is_active"] == "1":
            p["promo"] = promo
        else:
            p["promos_encerradas"].append(promo)

# manual de políticas: seções "## [topico] Título"
_manual = re.sub(r"<!--.*?-->", "", (ROOT / "knowledge" / "politicas.md").read_text(encoding="utf-8"), flags=re.S)
POLICIES = {k: v.strip() for k, v in re.findall(r"^## \[(\w+)\][^\n]*\n(.*?)(?=^## |\Z)", _manual, re.M | re.S)}


# ----------------------------------------------------------------------------- regras de negócio

def brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _preco(p: dict) -> float:
    """preço efetivo: com a promoção ativa, se houver."""
    return round(p["preco"] * (1 - p["promo"]["desconto"] / 100), 2) if p["promo"] else p["preco"]


def _disponibilidade(p: dict) -> str:
    if p["status"] == "discontinued":
        return "descontinuado (saiu do catálogo)"
    if p["status"] == "coming_soon":
        return "em breve (ainda não está à venda)"
    return "disponível" if p["estoque"] > 0 else "esgotado no momento"


def _max_parcelas(valor: float) -> int:
    """maior n (até 12) que respeita a parcela mínima: 2–3x R$ 50, 4–6x R$ 80, 7–12x R$ 100."""
    minimo = lambda n: 0 if n == 1 else 50 if n <= 3 else 80 if n <= 6 else 100  # noqa: E731
    return max(n for n in range(1, 13) if valor / n >= minimo(n))


def _resumo(p: dict) -> dict:
    preco = _preco(p)
    n = _max_parcelas(preco)
    out = {
        "id": p["id"],
        "nome": p["nome"],
        "categoria": p["categoria"],
        "disponibilidade": _disponibilidade(p),
        "preco_tabela": brl(p["preco"]),
    }
    if p["promo"]:
        out["promocao_ativa"] = f"{p['promo']['campanha']}: {p['promo']['desconto']:g}% off → {brl(preco)} (sem desconto extra no PIX)"
    else:
        out["preco_no_pix"] = brl(round(preco * 0.95, 2))
    out["cartao"] = f"até {n}x de {brl(preco / n)} sem juros"
    if p["promos_encerradas"]:
        out["promocoes_encerradas"] = [f"{x['campanha']} ({x['desconto']:g}%)" for x in p["promos_encerradas"]]
    if 0 < p["estoque"] <= 2 and p["status"] == "active":
        out["estoque"] = "últimas unidades"
    out["descricao"] = p["descricao"]
    out["especificacoes"] = p["specs"]
    return out


# ----------------------------------------------------------------------------- ferramentas

# Tipos simples (str, float, int, bool) de propósito: o SDK não converte argumentos para
# Literal nem para "float | None" e a ferramenta falharia. As opções válidas vão na docstring.

def buscar_produtos(termo: str = "", categoria: str = "", preco_max: float = 0, so_promocoes: bool = False) -> dict:
    """Busca instrumentos no catálogo. Use para qualquer pergunta sobre produto, preço, estoque ou
    promoção: um modelo específico ("quanto custa o Takamine GD20?"), uma busca aberta ("violões até
    R$ 1000") ou "tem algo em promoção?" (so_promocoes=true).

    Args:
        termo: marca, modelo ou característica (ex.: "Yamaha", "GD20", "nylon", "7 cordas").
        categoria: uma destas: Guitarras, Baixos, Baterias e Percussão, Teclados e Pianos, Violões,
            Instrumentos de Sopro (Madeiras), Instrumentos de Sopro (Metais), Cordas Orquestrais, Ukuleles.
        preco_max: preço máximo em reais, 0 = sem limite (considera o preço promocional, sem o desconto do PIX).
        so_promocoes: só produtos com promoção ativa.

    Retorna `disponiveis` (até 10, do mais barato ao mais caro) e, quando há `termo`, os produtos
    que batem com ele mas não estão à venda (`indisponiveis`: esgotado, descontinuado, em breve).
    """
    if categoria and categoria not in CATEGORIES.values():
        return {"erro": f"Categoria inválida: {categoria}", "categorias_validas": list(CATEGORIES.values())}
    pool = [p for p in PRODUCTS.values()
            if (not categoria or p["categoria"] == categoria)
            and (not preco_max or _preco(p) <= preco_max)
            and (not so_promocoes or p["promo"])]

    palavras = _words(termo)
    if palavras:
        compacto = re.sub(r"[^a-z0-9]", "", _norm(termo))  # "GD-20" == "gd20"
        exatos = [p for p in pool if len(compacto) >= 4 and compacto in p["nome_compacto"]]
        if exatos:
            pool = exatos
        else:  # fica com os produtos que batem com mais palavras do termo
            acertos = {p["id"]: sum(w in p["busca"] or w in p["nome_compacto"] for w in palavras) for p in pool}
            melhor = max(acertos.values(), default=0)
            pool = [p for p in pool if melhor and acertos[p["id"]] == melhor]

    pool.sort(key=_preco)
    disponiveis = [p for p in pool if _disponibilidade(p) == "disponível"]
    out = {"total_disponiveis": len(disponiveis), "disponiveis": [_resumo(p) for p in disponiveis[:10]]}
    if palavras:
        out["indisponiveis"] = [_resumo(p) for p in pool if p not in disponiveis][:5]
    if not pool:
        out["aviso"] = "Nenhum produto encontrado com esses filtros."
    return out


def calcular_pagamento(valor: float, preco_promocional: bool = False) -> dict:
    """Calcula PIX e parcelas no cartão para um VALOR TOTAL (ex.: soma de vários produtos).
    Para um produto só, o resultado de buscar_produtos já traz PIX e parcelas.

    Args:
        valor: valor total em reais.
        preco_promocional: true se o valor já tem desconto de promoção (aí o PIX não dá 5% extra).
    """
    n = _max_parcelas(valor)
    return {
        "valor": brl(valor),
        "pix": brl(valor) + " (sem desconto: preço promocional)" if preco_promocional else brl(round(valor * 0.95, 2)),
        "cartao": f"até {n}x de {brl(valor / n)} sem juros",
        "debito_ou_boleto": brl(valor),
        "pode_combinar_formas": valor > 2000,
    }


def consultar_politicas(topico: str) -> dict:
    """Lê uma seção do manual oficial da loja. Use antes de responder sobre endereço, contato,
    horário, formas de pagamento, trocas/devoluções, frete e prazos de entrega, rastreio, regras de
    promoção, atendimento (acessórios, reclamações), garantia ou privacidade.

    Args:
        topico: um destes: sobre_loja, horario, pagamento, trocas_devolucoes, frete_entrega,
            rastreamento, promocoes, atendimento, garantia, privacidade.
    """
    if topico not in POLICIES:
        return {"erro": f"Tópico inválido: {topico}", "topicos_validos": list(POLICIES)}
    return {"topico": topico, "texto": POLICIES[topico]}


STATUS = {
    "pending": "Pendente: aguardando confirmação do pagamento",
    "confirmed": "Confirmado: pagamento aprovado, em separação",
    "shipped": "Enviado: a caminho do endereço de entrega",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}


def _contato_confere(cliente: dict, contato: str) -> bool:
    if "@" in contato:
        return _norm(contato.strip()) == _norm(cliente["email"])
    digitos = re.sub(r"\D", "", contato)
    return len(digitos) >= 8 and re.sub(r"\D", "", cliente["phone"]).endswith(digitos[-9:])


def _pagamento(codigo: str) -> str:
    if codigo.startswith("credit_"):
        return f"cartão de crédito em {codigo[7:].rstrip('x')}x"
    return {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto"}.get(codigo, codigo)


def consultar_pedido(numero_pedido: int, contato: str) -> dict:
    """Status, itens, rastreio e prazos de devolução/troca/garantia (já calculados) de um pedido.
    Exige o número do pedido E o e-mail ou telefone cadastrado (política de privacidade): peça os
    dois ao cliente antes de chamar.

    Args:
        numero_pedido: número do pedido.
        contato: e-mail ou telefone informado pelo cliente.
    """
    o = ORDERS.get(int(numero_pedido))
    if not o or not _contato_confere(CUSTOMERS[int(o["customer_id"])], contato):
        # mesma mensagem para "não existe" e "não é seu", para não revelar pedidos de terceiros
        return {"erro": "Não encontrei pedido com esses dados. Confira o número e o e-mail/telefone da compra."}
    hoje = now().date()
    compra = date.fromisoformat(o["order_date"])
    previsao = date.fromisoformat(o["estimated_delivery"]) if o["estimated_delivery"] else None
    out = {
        "numero": numero_pedido,
        "cliente": CUSTOMERS[int(o["customer_id"])]["name"].split()[0],
        "data_compra": compra.isoformat(),
        "status": STATUS[o["status"]],
        "itens": [f"{i['quantity']}x {PRODUCTS[int(i['product_id'])]['nome']}" for i in o["items"]],
        "total": brl(float(o["total_brl"])),
        "pagamento": _pagamento(o["payment_method"]),
        "rastreio": o["tracking_code"] or None,
        "observacoes": o["notes"] or None,
    }
    if o["status"] == "shipped" and previsao:
        out["previsao_entrega"] = previsao.isoformat()
        if previsao < hoje:
            out["alerta"] = f"Previsão de entrega vencida há {(hoje - previsao).days} dias: ofereça encaminhar para a equipe."
    if o["status"] == "delivered" and previsao:
        def prazo(base: date, dias: int) -> str:
            fim = base + timedelta(days=dias)
            return f"até {fim:%d/%m/%Y} ({'dentro' if hoje <= fim else 'fora'} do prazo)"
        out["recebido_em"] = f"{previsao.isoformat()} (considerada a previsão de entrega; o sistema não registra a data real)"
        out["prazos"] = {
            "arrependimento_ou_troca_por_preferencia (7 dias do recebimento)": prazo(previsao, 7),
            "troca_por_defeito_na_loja (30 dias da compra)": prazo(compra, 30),
            "garantia_legal (90 dias do recebimento)": prazo(previsao, 90),
        }
    return out


def encaminhar_para_equipe(motivo: str, resumo: str, contato_cliente: str = "", numero_pedido: int = 0) -> dict:
    """Registra o caso para a equipe humana e gera um protocolo. Use para reclamação, devolução,
    troca, cancelamento, atraso, cotação de frete para outra cidade ou quando o cliente pedir um
    humano. Confirme com o cliente antes de registrar.

    Args:
        motivo: reclamacao, devolucao_ou_troca, cancelamento, atraso_entrega, cotacao_frete, garantia,
            atendimento_humano ou outro.
        resumo: resumo objetivo do caso para a equipe.
        contato_cliente: e-mail ou telefone do cliente.
        numero_pedido: número do pedido, 0 se não houver.
    """
    protocolo = f"EM-{now():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    LOGS_DIR.mkdir(exist_ok=True)
    with open(LOGS_DIR / "encaminhamentos.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"protocolo": protocolo, "em": now().isoformat(), "motivo": motivo, "resumo": resumo,
                            "contato": contato_cliente, "pedido": numero_pedido or None}, ensure_ascii=False) + "\n")
    return {"protocolo": protocolo, "prazo_retorno": "até 24 horas úteis"}


TOOLS = [buscar_produtos, calcular_pagamento, consultar_politicas, consultar_pedido, encaminhar_para_equipe]
