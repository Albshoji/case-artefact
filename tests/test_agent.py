# testa o Agent sem chamar a API, com um chat falso

from types import SimpleNamespace

from google.genai import errors, types

from emporio import agent as agent_mod


class FakeChat:
    def __init__(self, history, reply):
        self.history, self.reply = list(history), reply

    def send_message(self, message):
        if isinstance(self.reply, Exception):
            raise self.reply
        self.history += [
            types.Content(role="user", parts=[types.Part.from_text(text=message)]),
            types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(
                name="consultar_politicas", args={"topico": "horario"}))]),
            types.Content(role="user", parts=[types.Part.from_function_response(
                name="consultar_politicas", response={"result": "09:00 às 18:00"})]),
            types.Content(role="model", parts=[types.Part.from_text(text=self.reply)]),
        ]
        return SimpleNamespace(text=self.reply)

    def get_history(self):
        return self.history


def make_agent(monkeypatch, tmp_path, replies, session_id="t1"):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(agent_mod, "SESSIONS_DIR", tmp_path)
    a = agent_mod.Agent(session_id=session_id)
    replies = iter(replies)
    a.client = SimpleNamespace(chats=SimpleNamespace(
        create=lambda model, config, history: FakeChat(history, next(replies))))
    return a


def test_resposta_ferramentas_e_historico_persistido(monkeypatch, tmp_path):
    a = make_agent(monkeypatch, tmp_path, ["Abrimos das 9h às 18h!"])
    reply, calls = a.send("Que horas abre?")
    assert reply == "Abrimos das 9h às 18h!"
    assert calls == [{"nome": "consultar_politicas", "args": {"topico": "horario"},
                      "resultado": {"result": "09:00 às 18:00"}}]
    assert len(agent_mod.Agent(session_id="t1").history) == 4  # retomado do disco


def test_cai_para_modelo_reserva_em_503(monkeypatch, tmp_path):
    a = make_agent(monkeypatch, tmp_path, [errors.ServerError(503, {}), "Oi!"])
    assert a.send("oi")[0] == "Oi!"
    assert a.model_used == a.models[1]


def test_todos_os_modelos_falham(monkeypatch, tmp_path):
    a = make_agent(monkeypatch, tmp_path, [errors.ServerError(503, {})] * len(agent_mod.Agent().models))
    assert a.send("oi") == (agent_mod.MENSAGEM_ERRO, [])
    assert a.history == []
