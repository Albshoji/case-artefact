"""Base de políticas: seções do manual indexadas por tópico.

O manual tem ~3 mil tokens e 10 seções bem delimitadas. Em vez de RAG vetorial (chunking +
embeddings + banco vetorial), o modelo escolhe o TÓPICO via function calling e recebe a seção
inteira. Isso é determinístico, auditável (dá para ver no log qual seção foi usada) e não
corta regras no meio, como pode acontecer com chunks.
"""

from __future__ import annotations

import re
from functools import lru_cache

from . import config

SECTION_RE = re.compile(r"^## \[(?P<key>[a-z_]+)\] (?P<title>.+)$", re.M)


@lru_cache(maxsize=1)
def load_sections() -> dict[str, dict]:
    text = config.POLICIES_FILE.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # remove comentários de curadoria
    matches = list(SECTION_RE.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m["key"]] = {"titulo": m["title"].strip(), "conteudo": text[m.end():end].strip()}
    return sections


def topics() -> list[str]:
    return list(load_sections())
