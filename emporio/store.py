"""Camada de dados: carrega os CSVs da loja, normaliza e expõe consultas de negócio.

Decisões de tratamento de dados (detalhes no README):
- CSVs são carregados em memória (65 produtos / 20 pedidos): sem necessidade de banco.
- `specs` (JSON em texto, com formatação inconsistente) é parseado para dict.
- Preço efetivo = preço com promoção ATIVA (`is_active=1`), se houver. Promoções inativas
  ficam guardadas como histórico para o agente responder "a promoção X ainda vale?".
- Disponibilidade é derivada de `status` + `stock_quantity`:
  active+estoque>0 → disponível; active+0 → esgotado; discontinued → descontinuado
  (não vendável, mesmo com estoque); coming_soon → em breve (não vendável).
- Data de entrega de pedidos `delivered` = `estimated_delivery` (não há data real de entrega).
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import config

CSV_PREFIX = "desafio_tecnico_ai_eng - "


# ----------------------------------------------------------------------------- texto

STOPWORDS = {
    "a", "o", "as", "os", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "nos", "nas",
    "um", "uma", "uns", "umas", "com", "para", "pra", "por", "ate", "que", "qual", "quais",
    "r", "reais", "preco", "valor", "modelo", "modelos", "opcao", "opcoes", "instrumento",
    "instrumentos", "tem", "voces", "vcs", "algum", "alguma",
}

# termos do cliente -> termos presentes nos dados
SYNONYMS = {
    "eletroacustico": "eletrico",
    "eletroacustica": "eletrico",
    "eletrica": "eletrico",
    "steel": "aco",
    "folk": "folk",
    "piano": "piano",
    "sintetizador": "synth",
    "synthesizer": "synth",
    "classico": "nylon",
}

SPEC_TRANSLATIONS = {"steel": "aço", "yes": "elétrico eletroacústico", "no": ""}


def norm(text: str) -> str:
    """minúsculas, sem acentos."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(text))


def singular(word: str) -> str:
    if len(word) <= 3 or word.isdigit():
        return word
    if word.endswith("oes") or word.endswith("aes"):
        return word[:-3] + "ao"
    if word.endswith("is") and len(word) > 4:  # "eletricos" já cai no 's'; "papeis" raro
        return word
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", norm(text))
    out = []
    for t in tokens:
        if drop_stopwords and t in STOPWORDS:
            continue
        t = singular(t)
        out.append(SYNONYMS.get(t, t))
    return out


# ----------------------------------------------------------------------------- modelos

@dataclass
class Promotion:
    promotion_id: int
    product_id: int
    discount_percent: float
    description: str
    is_active: bool


@dataclass
class Product:
    product_id: int
    name: str
    price: float
    category_id: int
    category: str
    description: str
    stock: int
    status: str
    specs: dict
    created_at: str
    active_promo: Promotion | None = None
    past_promos: list[Promotion] = field(default_factory=list)
    _tokens: set[str] = field(default_factory=set, repr=False)
    _name_tokens: set[str] = field(default_factory=set, repr=False)

    @property
    def effective_price(self) -> float:
        if self.active_promo:
            return round(self.price * (1 - self.active_promo.discount_percent / 100), 2)
        return self.price

    @property
    def availability(self) -> str:
        if self.status == "discontinued":
            return "descontinuado"
        if self.status == "coming_soon":
            return "em_breve"
        if self.stock <= 0:
            return "esgotado"
        return "disponivel"

    @property
    def sellable(self) -> bool:
        return self.availability == "disponivel"


@dataclass
class Customer:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass
class OrderItem:
    product_id: int
    quantity: int


@dataclass
class Order:
    order_id: int
    customer_id: int
    order_date: date
    status: str
    total: float
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: list[OrderItem] = field(default_factory=list)


# ----------------------------------------------------------------------------- carga

def _read(name: str, data_dir: Path) -> list[dict]:
    with open(data_dir / f"{CSV_PREFIX}{name}.csv", encoding="utf-8") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _parse_specs(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def _opt_date(raw: str) -> date | None:
    return date.fromisoformat(raw) if raw else None


class Store:
    def __init__(self, data_dir: Path = config.DATA_DIR):
        self.categories: dict[int, dict] = {
            int(r["category_id"]): {"id": int(r["category_id"]), "nome": r["name"], "descricao": r["description"]}
            for r in _read("categories", data_dir)
        }

        promos = [
            Promotion(int(r["promotion_id"]), int(r["product_id"]), float(r["discount_percent"]),
                      r["description"], r["is_active"] == "1")
            for r in _read("promotions", data_dir)
        ]

        self.products: dict[int, Product] = {}
        for r in _read("products", data_dir):
            cat_id = int(r["category_id"])
            p = Product(
                product_id=int(r["product_id"]),
                name=r["name"],
                price=float(r["price_brl"]),
                category_id=cat_id,
                category=self.categories.get(cat_id, {}).get("nome", "Outros"),
                description=r["description"],
                stock=int(r["stock_quantity"] or 0),
                status=r["status"],
                specs=_parse_specs(r["specs"]),
                created_at=r["created_at"],
            )
            self.products[p.product_id] = p

        for promo in promos:
            p = self.products.get(promo.product_id)
            if not p:
                continue
            if promo.is_active:
                # se houver mais de uma ativa, vale a de maior desconto
                if not p.active_promo or promo.discount_percent > p.active_promo.discount_percent:
                    p.active_promo = promo
            else:
                p.past_promos.append(promo)

        for p in self.products.values():
            spec_text = " ".join(
                f"{v} cordas" if k == "strings" and str(v).isdigit() else SPEC_TRANSLATIONS.get(str(v), str(v))
                for k, v in p.specs.items()
            )
            p._name_tokens = set(tokenize(p.name))
            p._tokens = p._name_tokens | set(tokenize(f"{p.category} {p.description} {spec_text}"))

        self.customers: dict[int, Customer] = {
            int(r["customer_id"]): Customer(int(r["customer_id"]), r["name"], r["phone"], r["email"], r["city"])
            for r in _read("customers", data_dir)
        }

        self.orders: dict[int, Order] = {}
        for r in _read("orders", data_dir):
            o = Order(
                order_id=int(r["order_id"]),
                customer_id=int(r["customer_id"]),
                order_date=date.fromisoformat(r["order_date"]),
                status=r["status"],
                total=float(r["total_brl"]),
                payment_method=r["payment_method"],
                tracking_code=r["tracking_code"] or None,
                estimated_delivery=_opt_date(r["estimated_delivery"]),
                notes=r["notes"] or None,
            )
            self.orders[o.order_id] = o
        for r in _read("order_items", data_dir):
            o = self.orders.get(int(r["order_id"]))
            if o:
                o.items.append(OrderItem(int(r["product_id"]), int(r["quantity"])))

    # ------------------------------------------------------------------ produtos

    def category_by_name(self, name: str) -> dict | None:
        key = compact(name)
        for c in self.categories.values():
            if compact(c["nome"]) == key:
                return c
        # aceita aproximações ("violao", "sopro metais", ...)
        q = set(tokenize(name))
        best = max(self.categories.values(), key=lambda c: len(q & set(tokenize(c["nome"]))), default=None)
        if best and q & set(tokenize(best["nome"])):
            return best
        return None

    def score(self, product: Product, query: str) -> tuple[int, int]:
        """(tokens da busca encontrados, tokens encontrados no NOME). 0 se nada bate."""
        q_tokens = tokenize(query)
        if not q_tokens:
            return (0, 0)
        name_compact = compact(product.name)
        hits = name_hits = 0
        for t in q_tokens:
            in_name = t in product._name_tokens or (len(t) >= 3 and t in name_compact)
            in_any = in_name or t in product._tokens or (
                len(t) >= 4 and any(tok.startswith(t) for tok in product._tokens)
            )
            hits += in_any
            name_hits += in_name
        # "GD-20" / "gd 20" -> "gd20"
        q_compact = compact(query)
        if len(q_compact) >= 4 and q_compact in name_compact:
            name_hits = max(name_hits, len(q_tokens))
            hits = max(hits, len(q_tokens))
        return (hits, name_hits)

    def search(self, query: str | None = None, category_id: int | None = None,
               price_min: float | None = None, price_max: float | None = None,
               only_available: bool = True) -> tuple[list[Product], bool]:
        """Retorna (produtos, correspondencia_exata)."""
        pool = list(self.products.values())
        if category_id is not None:
            pool = [p for p in pool if p.category_id == category_id]
        if only_available:
            pool = [p for p in pool if p.sellable]
        else:
            pool = [p for p in pool if p.status != "discontinued"]
        if price_min is not None:
            pool = [p for p in pool if p.effective_price >= price_min]
        if price_max is not None:
            pool = [p for p in pool if p.effective_price <= price_max]

        if not query or not tokenize(query):
            return sorted(pool, key=lambda p: p.effective_price), True

        n = len(tokenize(query))
        scored = [(self.score(p, query), p) for p in pool]
        exact = [p for (h, _), p in scored if h >= n]
        if exact:
            exact.sort(key=lambda p: p.effective_price)
            return exact, True
        partial = [(s, p) for s, p in scored if s[0] > 0]
        partial.sort(key=lambda sp: (-sp[0][0], -sp[0][1], sp[1].effective_price))
        return [p for _, p in partial], False

    def find_product(self, query: str) -> list[Product]:
        """Localiza um produto específico por id ou nome. Lista vazia = nada; >1 = ambíguo."""
        q = query.strip().lstrip("#")
        if q.isdigit() and int(q) in self.products:
            return [self.products[int(q)]]
        scored = [(self.score(p, query), p) for p in self.products.values()]
        scored = [(s, p) for s, p in scored if s[1] > 0]
        if not scored:
            return []
        scored.sort(key=lambda sp: (-sp[0][1], -sp[0][0]))
        best = scored[0][0]
        top = [p for s, p in scored if s == best]
        return top

    def alternatives(self, product: Product, limit: int = 3) -> list[Product]:
        same_cat = [p for p in self.products.values()
                    if p.category_id == product.category_id and p.sellable and p.product_id != product.product_id]
        same_cat.sort(key=lambda p: abs(p.effective_price - product.effective_price))
        return same_cat[:limit]

    # ------------------------------------------------------------------ pedidos

    def customer_matches(self, customer: Customer, contact: str) -> bool:
        contact = contact.strip()
        if "@" in contact:
            return norm(contact) == norm(customer.email)
        digits = re.sub(r"\D", "", contact)
        cust_digits = re.sub(r"\D", "", customer.phone)
        return len(digits) >= 8 and cust_digits.endswith(digits[-9:] if len(digits) >= 9 else digits)

    def customer_by_contact(self, contact: str) -> Customer | None:
        for c in self.customers.values():
            if self.customer_matches(c, contact):
                return c
        return None


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store()
