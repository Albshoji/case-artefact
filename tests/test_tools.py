import pytest
from google.genai import types

from emporio import tools
from emporio.prompts import status_loja


@pytest.fixture(autouse=True)
def data_fixa(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_TODAY", "2026-03-25")
    monkeypatch.setattr(tools, "LOGS_DIR", tmp_path)


def nomes(r, campo="disponiveis"):
    return [p["nome"] for p in r[campo]]


def test_violoes_ate_1000_so_disponiveis():
    r = tools.buscar_produtos(categoria="Violões", preco_max=1000)
    assert r["total_disponiveis"] == 12
    assert "Giannini GF-3D Dreadnought Sunburst" not in nomes(r)  # estoque 0
    assert "Shelby SN-7C 7 Cordas Nylon Natural" not in nomes(r)  # descontinuado


def test_preco_takamine_gd20_e_promocao_encerrada():
    p = tools.buscar_produtos("Takamine GD-20")["disponiveis"][0]
    assert p["nome"] == "Takamine GD20 Dreadnought Natural"
    assert p["preco_tabela"] == "R$ 2.199,00"
    assert p["preco_no_pix"] == "R$ 2.089,05"
    assert "promocao_ativa" not in p
    assert p["promocoes_encerradas"]


def test_promocao_ativa_sem_pix():
    p = tools.buscar_produtos("Ohana CK-20")["disponiveis"][0]
    assert "R$ 439,20" in p["promocao_ativa"]
    assert "preco_no_pix" not in p


def test_filtro_de_preco_usa_preco_promocional():
    # Crafter HT-100 custa 2399, com 18% off sai 1967,18
    assert "Crafter HT-100 Folk Aço Natural" in nomes(tools.buscar_produtos("Crafter", preco_max=2000))


def test_produto_esgotado_aparece_como_indisponivel():
    r = tools.buscar_produtos("Giannini GF-3D")
    assert r["indisponiveis"][0]["disponibilidade"] == "esgotado no momento"


def test_produto_em_breve():
    r = tools.buscar_produtos("Kala KA-ABP-CTG")
    assert r["indisponiveis"][0]["disponibilidade"].startswith("em breve")


def test_produto_inexistente():
    assert "aviso" in tools.buscar_produtos("Stradivarius 1715")


def test_categoria_sem_produtos():
    assert tools.buscar_produtos(categoria="Cordas Orquestrais")["total_disponiveis"] == 0


def test_promocoes_ativas():
    assert tools.buscar_produtos(so_promocoes=True)["total_disponiveis"] == 4


@pytest.mark.parametrize("valor,parcelas", [(2199, 12), (599, 6), (159.9, 3), (90, 1), (1000, 10)])
def test_parcelamento(valor, parcelas):
    assert tools.calcular_pagamento(valor)["cartao"].startswith(f"até {parcelas}x")


def test_pix_e_combinacao():
    assert tools.calcular_pagamento(1000)["pix"] == "R$ 950,00"
    assert "sem desconto" in tools.calcular_pagamento(1000, preco_promocional=True)["pix"]
    assert tools.calcular_pagamento(2500)["pode_combinar_formas"] is True
    assert tools.calcular_pagamento(1500)["pode_combinar_formas"] is False


def test_politicas():
    assert len(tools.POLITICAS) == 10
    assert "09:00 às 18:00" in tools.consultar_politicas("horario")["texto"]
    assert "3341-4444" in tools.consultar_politicas("sobre_loja")["texto"]
    assert "topicos_validos" in tools.consultar_politicas("inexistente")
    assert "categorias_validas" in tools.buscar_produtos(categoria="Violinos")


def test_pedido_exige_contato_correto():
    assert "erro" in tools.consultar_pedido(1, "outra.pessoa@jmail.com")
    assert "erro" in tools.consultar_pedido(999, "pedro.oliveira@jmail.com")
    r = tools.consultar_pedido(1, "pedro.oliveira@jmail.com")
    assert r["status"] == "Entregue"
    assert r["cliente"] == "Pedro"
    assert r["pagamento"] == "PIX"


def test_pedido_por_telefone_sem_ddd_e_atraso():
    r = tools.consultar_pedido(8, "99654-7821")
    assert r["status"].startswith("Enviado")
    assert "vencida" in r["alerta"]  # previsão 28/02, hoje 25/03


def test_prazos_de_devolucao():
    r = tools.consultar_pedido(7, "leticia.rocha@jmail.com")  # recebido 17/02, hoje 25/03
    prazos = list(r["prazos"].values())
    assert "fora" in prazos[0] and "fora" in prazos[1] and "dentro" in prazos[2]


def test_encaminhamento_gera_protocolo(tmp_path):
    r = tools.encaminhar_para_equipe("reclamacao", "Atraso na entrega", "x@y.com", 8)
    assert r["protocolo"].startswith("EM-20260325-")
    assert (tmp_path / "encaminhamentos.jsonl").exists()


def test_sdk_gera_schema_de_todas_as_ferramentas():
    for fn in tools.TOOLS:
        decl = types.FunctionDeclaration.from_callable_with_api_option(callable=fn, api_option="GEMINI_API")
        assert decl.name == fn.__name__ and decl.description


@pytest.mark.parametrize("fn,args", [
    (tools.buscar_produtos, {"categoria": "Violões", "preco_max": 1000}),       # número inteiro vindo do modelo
    (tools.buscar_produtos, {"termo": "Takamine GD20", "preco_max": 999.9}),
    (tools.buscar_produtos, {"so_promocoes": True}),
    (tools.calcular_pagamento, {"valor": 2500, "preco_promocional": False}),
    (tools.consultar_politicas, {"topico": "garantia"}),
    (tools.consultar_pedido, {"numero_pedido": 7, "contato": "leticia.rocha@jmail.com"}),
    (tools.consultar_pedido, {"numero_pedido": 7.0, "contato": "leticia.rocha@jmail.com"}),
    (tools.encaminhar_para_equipe, {"motivo": "atraso_entrega", "resumo": "Pedido 8 atrasado", "numero_pedido": 8}),
])
def test_ferramentas_pelo_caminho_do_sdk(fn, args):
    # roda do mesmo jeito que o SDK roda, com a conversão de argumentos (foi aqui que o Literal quebrava)
    from google.genai import _extra_utils
    result = _extra_utils.invoke_function_from_dict_args(
        _extra_utils.convert_number_values_for_dict_function_call_args(args), fn)
    assert "erro" not in result


def test_status_da_loja():
    from datetime import datetime
    tz = tools.TZ
    assert status_loja(datetime(2026, 3, 25, 10, 30, tzinfo=tz)).startswith("ABERTA")
    assert "segunda-feira" in status_loja(datetime(2026, 3, 28, 14, 0, tzinfo=tz))  # sábado à tarde
    assert "amanhã" in status_loja(datetime(2026, 3, 29, 10, 0, tzinfo=tz))         # domingo
