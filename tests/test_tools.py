"""Testes determinísticos das ferramentas (não chamam o LLM)."""

import pytest

from emporio import tools


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_TODAY", "2026-03-25")
    monkeypatch.setattr(tools.config, "LOGS_DIR", tmp_path)


def names(result):
    return [p["nome"] for p in result["produtos"]]


# ------------------------------------------------------------------ catálogo

def test_violoes_ate_1000_somente_disponiveis():
    r = tools.buscar_produtos(categoria="Violões", preco_max=1000, limite=20)
    assert r["total_encontrado"] == 12
    assert "Giannini GF-3D Dreadnought Sunburst" not in names(r)  # estoque 0
    assert "Shelby SN-7C 7 Cordas Nylon Natural" not in names(r)  # descontinuado


def test_preco_takamine_gd20_sem_promocao_ativa():
    r = tools.detalhes_produto("Takamine GD-20")
    assert r["nome"] == "Takamine GD20 Dreadnought Natural"
    assert r["preco_tabela"] == "R$ 2.199,00"
    assert "promocao_ativa" not in r
    assert r["preco_no_pix"] == "R$ 2.089,05"
    assert r["promocoes_encerradas"][0]["campanha"] == "Oferta Especial"


def test_promocao_ativa_aplicada_e_pix_nao_cumulativo():
    r = tools.detalhes_produto("Ohana CK-20")
    assert r["promocao_ativa"]["preco_promocional"] == "R$ 439,20"
    assert "preco_no_pix" not in r


def test_filtro_de_preco_usa_preco_promocional():
    # Crafter HT-100 custa 2399, mas está com 18% off -> 1967,18
    r = tools.buscar_produtos(termo="Crafter", preco_max=2000)
    assert "Crafter HT-100 Folk Aço Natural" in names(r)


def test_produto_esgotado_sugere_alternativas():
    r = tools.detalhes_produto("Giannini GF-3D")
    assert r["disponibilidade"].startswith("esgotado")
    assert len(r["alternativas_disponiveis"]) == 3
    assert all(a["disponibilidade"] == "disponível" for a in r["alternativas_disponiveis"])


def test_produto_em_breve_nao_e_vendavel():
    r = tools.detalhes_produto("Kala KA-ABP-CTG")
    assert r["disponibilidade"].startswith("em breve")


def test_produto_inexistente():
    assert "erro" in tools.detalhes_produto("Stradivarius 1715")


def test_nome_ambiguo():
    r = tools.detalhes_produto("Martin D-28")
    assert r.get("ambiguo") or r["nome"].startswith("Martin")


def test_categorias_sem_estoque():
    cats = {c["nome"]: c["produtos_disponiveis"] for c in tools.listar_categorias()["categorias"]}
    assert cats["Cordas Orquestrais"] == 0
    assert cats["Violões"] > 0


def test_promocoes_ativas():
    assert tools.listar_promocoes_ativas()["total"] == 4


# ------------------------------------------------------------------ pagamento / frete

@pytest.mark.parametrize("valor,max_n", [(2199, 12), (599, 6), (159.9, 3), (90, 1), (1000, 10)])
def test_parcelamento(valor, max_n):
    r = tools.calcular_condicoes_pagamento(valor)
    assert r["cartao_credito"]["max_parcelas_sem_juros"] == max_n


def test_combinacao_pagamento_acima_de_2000():
    assert tools.calcular_condicoes_pagamento(2500)["combinar_formas_de_pagamento"] == "permitido"
    assert "não" in tools.calcular_condicoes_pagamento(1500)["combinar_formas_de_pagamento"]


def test_frete():
    assert tools.calcular_frete(600, "Campo Grande")["frete"] == "grátis"
    assert tools.calcular_frete(400, "campo grande")["frete"] == "R$ 35,00"
    assert "cotação" in tools.calcular_frete(600, "Dourados")["frete"]


# ------------------------------------------------------------------ políticas

def test_politicas_por_topico():
    r = tools.consultar_politicas("horario")
    assert "09:00 às 18:00" in r["conteudo"]
    assert "erro" in tools.consultar_politicas("inexistente")
    assert "3341-4444" in tools.consultar_politicas("sobre_loja")["conteudo"]


# ------------------------------------------------------------------ pedidos

def test_pedido_exige_contato_correto():
    assert "erro" in tools.consultar_pedido("outra.pessoa@jmail.com", 1)
    r = tools.consultar_pedido("pedro.oliveira@jmail.com", 1)
    assert r["status"] == "Entregue"
    assert r["cliente"] == "Pedro"


def test_pedido_por_telefone_sem_ddd():
    r = tools.consultar_pedido("99654-7821", 8)
    assert r["status"] == "Enviado"
    assert "alerta" in r  # previsão 28/02 vencida em 25/03


def test_lista_pedidos_do_cliente():
    r = tools.consultar_pedido("pedro.oliveira@jmail.com")
    assert [p["numero_pedido"] for p in r["pedidos"]] == [19, 1]


def test_prazos_de_devolucao_calculados():
    store = tools.get_store()
    cust = store.customers[store.orders[7].customer_id]
    r = tools.consultar_pedido(cust.email, 7)  # entregue em 17/02/2026, hoje 25/03/2026
    assert r["dias_desde_recebimento"] == 36
    assert r["prazos"]["arrependimento_7_dias_apos_recebimento"]["dentro_do_prazo"] is False
    assert r["prazos"]["troca_por_defeito_na_loja_30_dias_apos_compra"]["dentro_do_prazo"] is False
    assert r["prazos"]["garantia_legal_90_dias_apos_recebimento"]["dentro_do_prazo"] is True


def test_encaminhamento_gera_protocolo(tmp_path):
    r = tools.encaminhar_para_equipe("reclamacao", "Cliente reclamou de atraso", "x@y.com", 8)
    assert r["protocolo"].startswith("EM-20260325-")
    assert (tmp_path / "encaminhamentos.jsonl").exists()


def test_execute_trata_erros():
    assert "erro" in tools.execute("nao_existe", {})
    assert "erro" in tools.execute("detalhes_produto", {"parametro_errado": 1})


def test_declarations_cobrem_registry():
    assert {d["name"] for d in tools.declarations()} == set(tools.REGISTRY)
