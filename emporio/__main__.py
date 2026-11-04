import argparse
import json

from .agent import Agent

parser = argparse.ArgumentParser(description="Tom, atendente virtual da Empório da Música")
parser.add_argument("--sessao", help="id da conversa, pra continuar de onde parou")
parser.add_argument("--debug", action="store_true", help="mostra as ferramentas chamadas")
args = parser.parse_args()

agent = Agent(session_id=args.sessao)
print(f"Empório da Música - sessão {agent.session_id} (/nova reinicia, /sair encerra)\n")

while True:
    try:
        msg = input("Você: ").strip()
    except (EOFError, KeyboardInterrupt):
        break

    if not msg:
        continue
    if msg == "/sair":
        break
    if msg == "/nova":
        agent.reset()
        print("(conversa reiniciada)\n")
        continue

    try:
        resposta, chamadas = agent.send(msg)
    except Exception as e:
        print(f"[erro: {e}]\n")
        continue

    if args.debug:
        for c in chamadas:
            resultado = json.dumps(c["resultado"], ensure_ascii=False)
            print(f"  > {c['nome']}({json.dumps(c['args'], ensure_ascii=False)}) = {resultado[:300]}")
    print(f"Tom: {resposta}\n")

print(f"\nPra continuar essa conversa depois: python -m emporio --sessao {agent.session_id}")
