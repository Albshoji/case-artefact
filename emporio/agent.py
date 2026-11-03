"""Loop do agente: Gemini + function calling manual + histórico persistente.

O loop é manual (em vez do "automatic function calling" do SDK) para termos controle de:
limite de passos, tratamento de erros por ferramenta, rastro (trace) das chamadas para
debug/exemplos e persistência do histórico.
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from google import genai
from google.genai import errors, types

from . import config, tools
from .prompts import build_system_prompt

MAX_TOOL_STEPS = 8          # rodadas de ferramentas por mensagem do cliente
MAX_HISTORY_CONTENTS = 60   # janela de histórico enviada ao modelo
FALLBACK_REPLY = ("Desculpa, tive um probleminha técnico aqui. 😕 Pode tentar de novo em instantes? "
                  "Se preferir, fale com a equipe pelo (67) 3341-4444.")


@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict


@dataclass
class Turn:
    user: str
    reply: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class Agent:
    def __init__(self, session_id: str | None = None, model: str | None = None,
                 persist: bool = True, on_tool: Callable[[ToolCall], None] | None = None):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Defina GEMINI_API_KEY (veja .env.example).")
        self.client = genai.Client(api_key=api_key)
        self.model = model or config.model_name()
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.persist = persist
        self.on_tool = on_tool
        self.history: list[types.Content] = []
        self.tool_config = types.Tool(function_declarations=[
            types.FunctionDeclaration(**d) for d in tools.declarations()
        ])
        if persist:
            self._load()

    # ------------------------------------------------------------------ persistência

    @property
    def session_file(self):
        return config.SESSIONS_DIR / f"{self.session_id}.json"

    def _load(self) -> None:
        if self.session_file.exists():
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
            self.history = [types.Content.model_validate(c) for c in data["history"]]

    def _save(self) -> None:
        if not self.persist:
            return
        config.SESSIONS_DIR.mkdir(exist_ok=True)
        data = {
            "session_id": self.session_id,
            "model": self.model,
            "updated_at": config.now().isoformat(),
            "history": [c.model_dump(mode="json", exclude_none=True) for c in self.history],
        }
        self.session_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def reset(self) -> None:
        self.history = []
        if self.session_file.exists():
            self.session_file.unlink()

    # ------------------------------------------------------------------ LLM

    def _window(self) -> list[types.Content]:
        """Últimas N mensagens, começando sempre numa mensagem de texto do usuário
        (para não cortar um par chamada/resposta de ferramenta no meio)."""
        if len(self.history) <= MAX_HISTORY_CONTENTS:
            return self.history
        window = self.history[-MAX_HISTORY_CONTENTS:]
        for i, c in enumerate(window):
            if c.role == "user" and c.parts and c.parts[0].text:
                return window[i:]
        return window

    def _generate(self) -> types.GenerateContentResponse:
        cfg = types.GenerateContentConfig(
            system_instruction=build_system_prompt(),
            tools=[self.tool_config],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.3,
        )
        delay = 2.0
        for attempt in range(6):
            try:
                return self.client.models.generate_content(model=self.model, contents=self._window(), config=cfg)
            except (errors.ServerError, errors.ClientError) as e:
                retryable = isinstance(e, errors.ServerError) or getattr(e, "code", None) == 429
                if not retryable or attempt == 5:
                    raise
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
        raise RuntimeError("unreachable")

    # ------------------------------------------------------------------ API pública

    def send(self, message: str) -> Turn:
        turn = Turn(user=message, reply="")
        checkpoint = len(self.history)
        self.history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        try:
            for _ in range(MAX_TOOL_STEPS):
                response = self._generate()
                candidate = response.candidates[0] if response.candidates else None
                if not candidate or not candidate.content or not candidate.content.parts:
                    turn.reply = FALLBACK_REPLY
                    break
                self.history.append(candidate.content)

                calls = response.function_calls or []
                if not calls:
                    turn.reply = (response.text or "").strip() or FALLBACK_REPLY
                    break

                parts = []
                for fc in calls:
                    args = dict(fc.args or {})
                    result = tools.execute(fc.name, args)
                    call = ToolCall(fc.name, args, result)
                    turn.tool_calls.append(call)
                    if self.on_tool:
                        self.on_tool(call)
                    parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
                self.history.append(types.Content(role="tool", parts=parts))
            else:
                # estourou o limite de passos: fecha o turno com uma resposta segura
                turn.reply = ("Hmm, essa ficou complexa pra mim. Posso deixar registrado para a equipe te "
                              "responder? Você também pode ligar no (67) 3341-4444.")
                self.history.append(types.Content(role="model", parts=[types.Part.from_text(text=turn.reply)]))
        except Exception:
            # não deixa o histórico inconsistente (ex.: chamada de ferramenta sem resposta)
            del self.history[checkpoint:]
            raise

        if turn.reply == FALLBACK_REPLY:
            del self.history[checkpoint:]  # turno descartado; cliente pode reenviar
        else:
            self._save()
        return turn
