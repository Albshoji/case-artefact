import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from . import tools
from .prompts import montar_prompt

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SESSIONS_DIR = ROOT / ".sessions"
MENSAGEM_ERRO = "Desculpa, tive um problema técnico aqui. Pode tentar de novo? Ou fale com a equipe no (67) 3341-4444."


class Agent:
    def __init__(self, session_id=None, persist=True):
        self.client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=60_000, retry_options=types.HttpRetryOptions(attempts=2)),
        )
        # no free tier é comum dar 503/429, então tento os modelos reserva na ordem
        reservas = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3-flash-preview,gemini-3.6-flash")
        self.models = [os.getenv("GEMINI_MODEL", "gemini-3.5-flash")]
        self.models += [m.strip() for m in reservas.split(",") if m.strip()]
        self.model_used = ""

        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.file = SESSIONS_DIR / f"{self.session_id}.json" if persist else None
        self.history = []
        if self.file and self.file.exists():
            dados = json.loads(self.file.read_text(encoding="utf-8"))
            self.history = [types.Content.model_validate(c) for c in dados]

    def send(self, message):
        """Manda a mensagem do cliente e devolve (resposta, ferramentas chamadas)."""
        config = types.GenerateContentConfig(
            system_instruction=montar_prompt(tools.now()),
            tools=tools.TOOLS,
            # o SDK executa as ferramentas sozinho, até 8 rodadas por mensagem
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8),
            temperature=0.3,
        )

        response = None
        for model in self.models:
            chat = self.client.chats.create(model=model, config=config, history=self.history)
            try:
                response = chat.send_message(message)
                break
            except errors.APIError as e:
                # 404 = modelo não disponível pra essa chave; os outros são sobrecarga/cota
                if e.code not in (404, 429, 500, 503):
                    raise

        if response is None or not response.text:
            return MENSAGEM_ERRO, []

        novas = chat.get_history()[len(self.history):]
        self.history = chat.get_history()
        self.model_used = model
        self.salvar()
        return response.text.strip(), self.chamadas(novas)

    def chamadas(self, mensagens):
        pedidos, respostas = [], []
        for msg in mensagens:
            for part in msg.parts or []:
                if part.function_call:
                    pedidos.append(part.function_call)
                if part.function_response:
                    respostas.append(part.function_response.response)
        return [
            {"nome": p.name, "args": dict(p.args or {}), "resultado": r}
            for p, r in zip(pedidos, respostas)
        ]

    def salvar(self):
        if not self.file:
            return
        SESSIONS_DIR.mkdir(exist_ok=True)
        dados = [c.model_dump(mode="json", exclude_none=True) for c in self.history]
        self.file.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    def reset(self):
        self.history = []
        if self.file and self.file.exists():
            self.file.unlink()
