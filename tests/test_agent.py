"""Testes do loop do agente com um modelo falso (sem rede)."""

from datetime import datetime

import pytest
from google.genai import types

from emporio import agent as agent_mod
from emporio import config
from emporio.prompts import build_system_prompt, store_status


def fc_response(name, args):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
        role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))])


def text_response(text):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
        role="model", parts=[types.Part.from_text(text=text)]))])


@pytest.fixture
def make_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("AGENT_TODAY", "2026-03-25")
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path)

    def factory(script, session_id="t1"):
        a = agent_mod.Agent(session_id=session_id)
        responses = iter(script)
        monkeypatch.setattr(a, "_generate", lambda: next(responses))
        return a
    return factory


def test_loop_executa_ferramenta_e_responde(make_agent):
    a = make_agent([
        fc_response("detalhes_produto", {"produto": "Takamine GD20"}),
        text_response("O Takamine GD20 sai por R$ 2.199,00."),
    ])
    turn = a.send("Quanto custa o Takamine GD20?")
    assert turn.reply == "O Takamine GD20 sai por R$ 2.199,00."
    assert turn.tool_calls[0].name == "detalhes_produto"
    assert turn.tool_calls[0].result["preco_tabela"] == "R$ 2.199,00"
    # user, model(call), tool(result), model(text)
    assert [c.role for c in a.history] == ["user", "model", "user", "model"]


def test_historico_persistido_e_retomado(make_agent):
    a = make_agent([text_response("Oi! Sou o Tom.")], session_id="persist")
    a.send("oi")
    b = make_agent([], session_id="persist")
    assert len(b.history) == 2
    assert b.history[1].parts[0].text == "Oi! Sou o Tom."


def test_resposta_vazia_descarta_turno(make_agent):
    a = make_agent([types.GenerateContentResponse(candidates=[])])
    turn = a.send("oi")
    assert turn.reply == agent_mod.FALLBACK_REPLY
    assert a.history == []


def test_erro_de_api_nao_corrompe_historico(make_agent, monkeypatch):
    a = make_agent([])

    def boom():
        raise RuntimeError("rede caiu")
    monkeypatch.setattr(a, "_generate", boom)
    with pytest.raises(RuntimeError):
        a.send("oi")
    assert a.history == []


def test_limite_de_passos(make_agent):
    a = make_agent([fc_response("listar_categorias", {})] * agent_mod.MAX_TOOL_STEPS)
    turn = a.send("loop")
    assert len(turn.tool_calls) == agent_mod.MAX_TOOL_STEPS
    assert a.history[-1].role == "model"


def test_status_da_loja_no_prompt():
    tz = config.TZ
    assert store_status(datetime(2026, 3, 25, 10, 30, tzinfo=tz)).startswith("ABERTA")
    assert "segunda-feira" in store_status(datetime(2026, 3, 28, 14, 0, tzinfo=tz))  # sábado à tarde
    assert "amanhã" in store_status(datetime(2026, 3, 29, 10, 0, tzinfo=tz))         # domingo
    assert "25/03/2026" in build_system_prompt(datetime(2026, 3, 25, 10, 30, tzinfo=tz))
