"""Chat no terminal.

    python -m emporio                  # nova conversa
    python -m emporio --sessao ana     # cria/retoma a conversa "ana"
    python -m emporio --debug          # mostra as ferramentas chamadas
"""

import argparse
import json

from .agent import Agent

parser = argparse.ArgumentParser(description="Tom, assistente virtual da Empório da Música")
parser.add_argument("--sessao", help="id da conversa para retomar o histórico")
parser.add_argument("--debug", action="store_true", help="mostra as ferramentas chamadas")
args = parser.parse_args()

agent = Agent(session_id=args.sessao)
print(f"🎸 Empório da Música (sessão {agent.session_id}). Comandos: /nova, /sair\n")

while True:
    try:
        msg = input("Você: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if msg == "/sair":
        break
    if msg == "/nova":
        agent.reset()
        print("(conversa reiniciada)\n")
        continue
    if not msg:
        continue
    try:
        reply, calls = agent.send(msg)
    except Exception as e:
        print(f"[erro ao falar com o modelo: {e}]\n")
        continue
    if args.debug:
        for c in calls:
            print(f"  ⚙ {c['nome']}({json.dumps(c['args'], ensure_ascii=False)}) → "
                  f"{json.dumps(c['resultado'], ensure_ascii=False)[:300]}")
    print(f"Tom: {reply}\n")

print(f"\nAté mais! Para retomar: python -m emporio --sessao {agent.session_id}")
