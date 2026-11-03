"""Configuração central: caminhos, fuso horário e data de referência."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
KNOWLEDGE_DIR = ROOT / "knowledge"
POLICIES_FILE = KNOWLEDGE_DIR / "politicas.md"
SESSIONS_DIR = ROOT / ".sessions"
LOGS_DIR = ROOT / "logs"

TZ = ZoneInfo("America/Campo_Grande")

DEFAULT_MODEL = "gemini-2.5-flash"


def model_name() -> str:
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODEL


def now() -> datetime:
    """Data/hora "atual" do agente.

    `AGENT_TODAY=YYYY-MM-DD` (opcional) fixa a data — útil porque os dados de pedidos
    são um retrato de março/2026 e os exemplos precisam ser reproduzíveis.
    `AGENT_TIME=HH:MM` (opcional) fixa a hora.
    """
    real = datetime.now(TZ)
    fixed_date = os.getenv("AGENT_TODAY")
    fixed_time = os.getenv("AGENT_TIME")
    d = date.fromisoformat(fixed_date) if fixed_date else real.date()
    if fixed_time:
        hh, mm = (int(x) for x in fixed_time.split(":"))
    else:
        hh, mm = real.hour, real.minute
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)


def today() -> date:
    return now().date()
