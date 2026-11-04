"""Agente: Gemini com function calling automático do SDK e histórico salvo em JSON.

O SDK chama as ferramentas sozinho (até 8 rodadas por mensagem) e devolve a resposta final.
Se um modelo estiver sobrecarregado ou sem cota, tenta o próximo da lista.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from . import tools
from .prompts import build_system_prompt

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
SESSIONS_DIR = ROOT / ".sessions"
ERRO = "Desculpa, tive um probleminha técnico aqui. 😕 Pode tentar de novo? Ou fale com a equipe no (67) 3341-4444."


class Agent:
    def __init__(self, session_id: str | None = None, persist: bool = True):
        self.client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=60_000, retry_options=types.HttpRetryOptions(attempts=2)),
        )
        self.models = [os.getenv("GEMINI_MODEL", "gemini-3.5-flash")] + [
            m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3-flash-preview,gemini-3.6-flash").split(",")
            if m.strip()]
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.file = SESSIONS_DIR / f"{self.session_id}.json" if persist else None
        self.history: list[types.Content] = []
        if self.file and self.file.exists():
            self.history = [types.Content.model_validate(c) for c in json.loads(self.file.read_text(encoding="utf-8"))]
        self.model_used = ""

    def send(self, message: str) -> tuple[str, list[dict]]:
        """Responde uma mensagem do cliente. Retorna (resposta, ferramentas chamadas com resultado)."""
        config = types.GenerateContentConfig(
            system_instruction=build_system_prompt(tools.now()),
            tools=tools.TOOLS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8),
            temperature=0.3,
        )
        for model in self.models:
            chat = self.client.chats.create(model=model, config=config, history=self.history)
            try:
                response = chat.send_message(message)
                break
            except errors.APIError as e:
                if e.code not in (404, 429, 500, 503):  # 404: modelo indisponível para a chave
                    raise
        else:
            return ERRO, []

        if not response.text:
            return ERRO, []
        new = chat.get_history()[len(self.history):]
        self.history = chat.get_history()
        self.model_used = model
        if self.file:
            SESSIONS_DIR.mkdir(exist_ok=True)
            self.file.write_text(json.dumps([c.model_dump(mode="json", exclude_none=True) for c in self.history],
                                            ensure_ascii=False), encoding="utf-8")
        parts = [p for c in new for p in (c.parts or [])]
        calls = [p.function_call for p in parts if p.function_call]
        results = [p.function_response.response for p in parts if p.function_response]
        return response.text.strip(), [{"nome": c.name, "args": dict(c.args or {}), "resultado": r}
                                       for c, r in zip(calls, results)]

    def reset(self) -> None:
        self.history = []
        if self.file and self.file.exists():
            self.file.unlink()
