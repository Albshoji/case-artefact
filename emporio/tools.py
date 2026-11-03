"""Ferramentas (function calling) que o agente pode chamar.

Princípio: o LLM decide QUANDO consultar e COMO comunicar; toda conta, filtro e regra
determinística (preço promocional, PIX, parcelamento, frete, prazos de devolução) é feita
aqui em Python. LLMs erram aritmética e datas; código não.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any, Callable

from . import config, policies
from .store import Order, Product, get_store

# ----------------------------------------------------------------------------- formatação

AVAILABILITY_LABELS = {
    "disponivel": "disponível",
    "esgotado": "esgotado no momento",
    "descontinuado": "descontinuado (não faz mais parte do catálogo)",
    "em_breve": "em breve (ainda não disponível para venda)",
}

SPEC_KEYS = {
    "top": "tampo", "back_sides": "fundo e laterais", "neck": "braço", "strings": "cordas",
    "scale": "escala", "electronics": "eletrônica/captação", "color": "cor", "body": "corpo",
    "shells": "cascos", "pieces": "peças", "hardware": "ferragens", "keys": "teclas",
    "type": "tipo", "polyphony": "polifonia",
}
SPEC_VALUES = {"steel": "aço", "yes": "sim", "no": "não", "included": "incluídas"}

ORDER_STATUS = {
    "pending": ("Pendente", "Pedido recebido, aguardando a confirmação do pagamento."),
    "confirmed": ("Confirmado", "Pagamento aprovado; pedido em separação, ainda não despachado."),
    "shipped": ("Enviado", "Pedido despachado e a caminho do endereço de entrega."),
    "delivered": ("Entregue", "Pedido entregue."),
    "cancelled": ("Cancelado", "Pedido cancelado."),
}


def brl(value: float) -> str:
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def payment_label(code: str) -> str:
    if code.startswith("credit_"):
        n = code.removeprefix("credit_").rstrip("x")
        return f"Cartão de crédito em {n}x"
    return {"pix": "PIX", "debit": "Cartão de débito", "boleto": "Boleto bancário"}.get(code, code)


def product_summary(p: Product) -> dict:
    out: dict[str, Any] = {
        "id": p.product_id,
        "nome": p.name,
        "categoria": p.category,
        "preco_tabela": brl(p.price),
        "disponibilidade": AVAILABILITY_LABELS[p.availability],
    }
    if p.active_promo:
        out["promocao_ativa"] = {
            "campanha": p.active_promo.description,
            "desconto": f"{p.active_promo.discount_percent:g}%",
            "preco_promocional": brl(p.effective_price),
            "obs": "Desconto PIX não é cumulativo com a promoção.",
        }
    elif p.sellable:
        out["preco_no_pix"] = brl(round(p.price * 0.95, 2))
    if p.sellable and p.stock <= 2:
        out["estoque"] = "últimas unidades"
    return out


# ----------------------------------------------------------------------------- produtos

def buscar_produtos(termo: str | None = None, categoria: str | None = None,
                    preco_min: float | None = None, preco_max: float | None = None,
                    incluir_indisponiveis: bool = False, ordenar: str = "preco_asc",
                    limite: int = 8) -> dict:
    store = get_store()
    category_id = None
    if categoria:
        cat = store.category_by_name(categoria)
        if not cat:
            return {"erro": f"Categoria '{categoria}' não existe.",
                    "categorias_validas": [c["nome"] for c in store.categories.values()]}
        category_id = cat["id"]

    results, exact = store.search(termo, category_id, preco_min, preco_max,
                                  only_available=not incluir_indisponiveis)
    if ordenar == "preco_desc":
        results = sorted(results, key=lambda p: -p.effective_price)
    limite = max(1, min(int(limite or 8), 20))
    out: dict[str, Any] = {
        "total_encontrado": len(results),
        "mostrando": min(limite, len(results)),
        "produtos": [product_summary(p) for p in results[:limite]],
        "filtro_preco_considera": "preço efetivo (promocional, se houver; sem desconto PIX)",
    }
    if termo and not exact and results:
        out["aviso"] = "Nenhum produto atende a TODOS os termos; resultados são correspondências parciais."
    if not results:
        out["aviso"] = "Nenhum produto disponível com esses filtros."
    return out


def detalhes_produto(produto: str) -> dict:
    store = get_store()
    found = store.find_product(str(produto))
    if not found:
        return {"erro": f"Nenhum produto encontrado para '{produto}'. Ele pode não fazer parte do catálogo."}
    if len(found) > 1:
        return {"ambiguo": True, "mensagem": "Mais de um produto corresponde; peça para o cliente especificar.",
                "candidatos": [product_summary(p) for p in found[:8]]}
    p = found[0]
    out = product_summary(p)
    out["descricao"] = p.description
    out["especificacoes"] = {SPEC_KEYS.get(k, k): SPEC_VALUES.get(str(v), v) for k, v in p.specs.items()}
    if p.past_promos:
        out["promocoes_encerradas"] = [
            {"campanha": pr.description, "desconto": f"{pr.discount_percent:g}%"} for pr in p.past_promos
        ]
    if not p.sellable:
        out["alternativas_disponiveis"] = [product_summary(a) for a in store.alternatives(p)]
    return out


def listar_categorias() -> dict:
    store = get_store()
    cats = []
    for c in store.categories.values():
        n = sum(1 for p in store.products.values() if p.category_id == c["id"] and p.sellable)
        cats.append({"nome": c["nome"], "descricao": c["descricao"], "produtos_disponiveis": n})
    return {"categorias": cats}


def listar_promocoes_ativas() -> dict:
    store = get_store()
    promos = [product_summary(p) for p in store.products.values() if p.active_promo]
    return {"promocoes_ativas": promos, "total": len(promos)}


# ----------------------------------------------------------------------------- pagamento / frete

def _min_installment(n: int) -> float:
    if n == 1:
        return 0
    if n <= 3:
        return 50
    if n <= 6:
        return 80
    return 100


def calcular_condicoes_pagamento(valor: float, preco_promocional: bool = False) -> dict:
    valor = float(valor)
    if valor <= 0:
        return {"erro": "Valor deve ser positivo."}
    parcelas = [
        {"vezes": n, "parcela": brl(valor / n)}
        for n in range(1, 13) if valor / n >= _min_installment(n)
    ]
    out: dict[str, Any] = {
        "valor": brl(valor),
        "cartao_credito": {
            "max_parcelas_sem_juros": parcelas[-1]["vezes"],
            "opcoes": parcelas,
        },
        "debito_ou_boleto": brl(valor),
        "combinar_formas_de_pagamento": "permitido" if valor > 2000 else "não permitido (só acima de R$ 2.000,00)",
    }
    if preco_promocional:
        out["pix"] = f"{brl(valor)} (desconto PIX não se aplica sobre preço promocional)"
    else:
        out["pix"] = f"{brl(round(valor * 0.95, 2))} (5% de desconto)"
    return out


def calcular_frete(valor_pedido: float, cidade: str) -> dict:
    from .store import norm
    valor = float(valor_pedido)
    if norm(cidade).strip() in {"campo grande", "cg"}:
        return {
            "regiao": "Campo Grande (entrega por motoboy próprio)",
            "frete": "grátis" if valor > 500 else brl(35),
            "regra": "Frete grátis acima de R$ 500,00; até R$ 500,00, taxa fixa de R$ 35,00.",
            "prazo": "1 a 3 dias úteis",
        }
    return {
        "regiao": f"Outra cidade ({cidade})",
        "frete": "sob cotação: depende do CEP, peso e dimensões; a equipe faz o cálculo",
        "modalidades": [
            {"modalidade": "PAC (Correios)", "prazo": "5 a 12 dias úteis"},
            {"modalidade": "SEDEX (Correios)", "prazo": "2 a 5 dias úteis"},
            {"modalidade": "Jadlog", "prazo": "3 a 8 dias úteis"},
        ],
        "obs": "Todos os envios têm rastreamento e seguro. Instrumentos de grande porte "
               "(baterias acústicas, pianos digitais, contrabaixos) podem exigir frete especial.",
    }


# ----------------------------------------------------------------------------- políticas

def consultar_politicas(topico: str) -> dict:
    sections = policies.load_sections()
    if topico not in sections:
        return {"erro": f"Tópico inválido: {topico}", "topicos_validos": list(sections)}
    return sections[topico]


# ----------------------------------------------------------------------------- pedidos

def _order_details(o: Order) -> dict:
    store = get_store()
    hoje = config.today()
    label, explicacao = ORDER_STATUS.get(o.status, (o.status, ""))
    customer = store.customers[o.customer_id]
    out: dict[str, Any] = {
        "numero_pedido": o.order_id,
        "cliente": customer.name.split()[0],
        "data_pedido": o.order_date.isoformat(),
        "status": label,
        "explicacao_status": explicacao,
        "itens": [
            {"produto": store.products[i.product_id].name if i.product_id in store.products else f"#{i.product_id}",
             "quantidade": i.quantity}
            for i in o.items
        ],
        "total": brl(o.total),
        "forma_pagamento": payment_label(o.payment_method),
    }
    if o.tracking_code:
        out["codigo_rastreio"] = o.tracking_code
    if o.notes:
        out["observacoes"] = o.notes

    if o.status == "shipped" and o.estimated_delivery:
        out["previsao_entrega"] = o.estimated_delivery.isoformat()
        if o.estimated_delivery < hoje:
            out["alerta"] = (f"Previsão de entrega vencida há {(hoje - o.estimated_delivery).days} dias. "
                             "Oferecer encaminhamento para a equipe verificar com a transportadora.")
        out["obs_arrependimento"] = "O prazo de 7 dias para arrependimento começa a contar no recebimento."
    elif o.status == "delivered" and o.estimated_delivery:
        recebido = o.estimated_delivery
        dias_receb = (hoje - recebido).days
        dias_compra = (hoje - o.order_date).days

        def janela(base, dias):
            fim = base + timedelta(days=dias)
            return {"prazo_final": fim.isoformat(), "dentro_do_prazo": hoje <= fim}

        out["data_recebimento_considerada"] = recebido.isoformat()
        out["dias_desde_recebimento"] = dias_receb
        out["dias_desde_compra"] = dias_compra
        out["prazos"] = {
            "arrependimento_7_dias_apos_recebimento": janela(recebido, 7),
            "troca_por_preferencia_7_dias": janela(recebido, 7),
            "troca_por_defeito_na_loja_30_dias_apos_compra": janela(o.order_date, 30),
            "garantia_legal_90_dias_apos_recebimento": janela(recebido, 90),
        }
        out["obs_prazos"] = ("Data de recebimento estimada pela previsão de entrega do sistema. "
                             "Após 30 dias da compra, defeitos são tratados via garantia do fabricante "
                             "(a loja pode intermediar).")
    return out


def consultar_pedido(contato: str, numero_pedido: int | None = None) -> dict:
    """`contato` = e-mail ou telefone cadastrado (verificação de identidade, LGPD)."""
    store = get_store()
    if not contato or not str(contato).strip():
        return {"erro": "Informe o e-mail ou telefone cadastrado para verificação."}
    nao_encontrado = {"erro": "Não encontrei pedido com esses dados. Confira o número do pedido e "
                              "o e-mail/telefone usados na compra."}
    if numero_pedido is not None:
        o = store.orders.get(int(numero_pedido))
        if not o or not store.customer_matches(store.customers[o.customer_id], str(contato)):
            return nao_encontrado
        return _order_details(o)

    customer = store.customer_by_contact(str(contato))
    if not customer:
        return nao_encontrado
    orders = sorted((o for o in store.orders.values() if o.customer_id == customer.customer_id),
                    key=lambda o: o.order_date, reverse=True)
    if not orders:
        return {"mensagem": "Cliente localizado, mas não há pedidos registrados."}
    return {
        "cliente": customer.name.split()[0],
        "pedidos": [{"numero_pedido": o.order_id, "data_pedido": o.order_date.isoformat(),
                     "status": ORDER_STATUS.get(o.status, (o.status,))[0], "total": brl(o.total)}
                    for o in orders],
    }


# ----------------------------------------------------------------------------- escalonamento

def encaminhar_para_equipe(motivo: str, resumo: str, contato_cliente: str | None = None,
                           numero_pedido: int | None = None) -> dict:
    protocolo = f"EM-{config.today():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    registro = {
        "protocolo": protocolo,
        "registrado_em": config.now().isoformat(),
        "motivo": motivo,
        "resumo": resumo,
        "contato_cliente": contato_cliente,
        "numero_pedido": numero_pedido,
    }
    config.LOGS_DIR.mkdir(exist_ok=True)
    with open(config.LOGS_DIR / "encaminhamentos.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {"protocolo": protocolo, "prazo_retorno": "até 24 horas úteis", "status": "registrado"}


# ----------------------------------------------------------------------------- registro

REGISTRY: dict[str, Callable[..., dict]] = {
    f.__name__: f for f in [
        buscar_produtos, detalhes_produto, listar_categorias, listar_promocoes_ativas,
        calcular_condicoes_pagamento, calcular_frete, consultar_politicas, consultar_pedido,
        encaminhar_para_equipe,
    ]
}


def declarations() -> list[dict]:
    """Schemas das ferramentas no formato function declaration (JSON Schema)."""
    store = get_store()
    cat_names = [c["nome"] for c in store.categories.values()]
    return [
        {
            "name": "buscar_produtos",
            "description": "Busca instrumentos no catálogo com filtros. Use para perguntas abertas "
                           "('quais violões até R$ 1000?', 'tem guitarra Fender?'). Retorna preço de "
                           "tabela, promoção ativa, preço no PIX e disponibilidade REAL de estoque.",
            "parameters_json_schema": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Palavras-chave: marca, modelo, tipo "
                              "(ex.: 'nylon', 'elétrico', 'Yamaha', '7 cordas', 'tenor')."},
                    "categoria": {"type": "string", "enum": cat_names},
                    "preco_min": {"type": "number"},
                    "preco_max": {"type": "number", "description": "Preço máximo em reais."},
                    "incluir_indisponiveis": {"type": "boolean", "description": "Inclui esgotados e "
                                              "lançamentos futuros. Padrão: false."},
                    "ordenar": {"type": "string", "enum": ["preco_asc", "preco_desc"]},
                    "limite": {"type": "integer", "description": "Máx. de itens (padrão 8, máx. 20)."},
                },
            },
        },
        {
            "name": "detalhes_produto",
            "description": "Detalhes de UM produto específico pelo nome/modelo ou id: preço, promoção "
                           "ativa e encerradas, especificações, estoque e alternativas se indisponível. "
                           "Use para 'quanto custa o X?', 'tem o X?', 'a promoção do X ainda vale?'.",
            "parameters_json_schema": {
                "type": "object",
                "properties": {"produto": {"type": "string", "description": "Nome, modelo ou id."}},
                "required": ["produto"],
            },
        },
        {
            "name": "listar_categorias",
            "description": "Lista as categorias de instrumentos e quantos produtos há disponíveis em cada.",
            "parameters_json_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "listar_promocoes_ativas",
            "description": "Lista todos os produtos com promoção ativa agora.",
            "parameters_json_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "calcular_condicoes_pagamento",
            "description": "Calcula preço no PIX, parcelamento máximo sem juros e opções de parcelas "
                           "para um valor, segundo as regras da loja.",
            "parameters_json_schema": {
                "type": "object",
                "properties": {
                    "valor": {"type": "number", "description": "Valor total em reais."},
                    "preco_promocional": {"type": "boolean", "description": "true se o valor já é "
                                          "preço promocional (PIX não acumula desconto)."},
                },
                "required": ["valor"],
            },
        },
        {
            "name": "calcular_frete",
            "description": "Informa frete e prazo de entrega para um valor de pedido e cidade de destino.",
            "parameters_json_schema": {
                "type": "object",
                "properties": {
                    "valor_pedido": {"type": "number"},
                    "cidade": {"type": "string"},
                },
                "required": ["valor_pedido", "cidade"],
            },
        },
        {
            "name": "consultar_politicas",
            "description": "Consulta o manual oficial de políticas da loja por tópico. Use SEMPRE antes "
                           "de responder sobre: endereço/contato, horário, pagamento, trocas/devoluções, "
                           "frete, rastreamento, regras de promoção, garantia, privacidade, escopo de "
                           "atendimento.",
            "parameters_json_schema": {
                "type": "object",
                "properties": {"topico": {"type": "string", "enum": policies.topics()}},
                "required": ["topico"],
            },
        },
        {
            "name": "consultar_pedido",
            "description": "Consulta status, itens, rastreio e prazos (devolução/troca/garantia já "
                           "calculados) de pedidos. Exige o e-mail OU telefone cadastrado do cliente. "
                           "Sem número do pedido, lista os pedidos do cliente.",
            "parameters_json_schema": {
                "type": "object",
                "properties": {
                    "contato": {"type": "string", "description": "E-mail ou telefone informado pelo cliente."},
                    "numero_pedido": {"type": "integer"},
                },
                "required": ["contato"],
            },
        },
        {
            "name": "encaminhar_para_equipe",
            "description": "Registra um atendimento para a equipe humana e gera protocolo. Use para: "
                           "reclamações, pedidos de devolução/troca/cancelamento, atraso de entrega, "
                           "cotação de frete para outras cidades, ou quando o cliente pedir um humano. "
                           "Confirme com o cliente antes de registrar.",
            "parameters_json_schema": {
                "type": "object",
                "properties": {
                    "motivo": {"type": "string", "enum": [
                        "reclamacao", "devolucao_ou_troca", "cancelamento", "atraso_entrega",
                        "cotacao_frete", "garantia", "atendimento_humano", "outro"]},
                    "resumo": {"type": "string", "description": "Resumo objetivo do caso para a equipe."},
                    "contato_cliente": {"type": "string"},
                    "numero_pedido": {"type": "integer"},
                },
                "required": ["motivo", "resumo"],
            },
        },
    ]


def execute(name: str, args: dict | None) -> dict:
    fn = REGISTRY.get(name)
    if not fn:
        return {"erro": f"Ferramenta desconhecida: {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"erro": f"Argumentos inválidos para {name}: {e}"}
    except Exception as e:  # nunca derrubar a conversa por erro de ferramenta
        return {"erro": f"Falha ao executar {name}: {e}"}
