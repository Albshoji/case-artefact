"""Interface de linha de comando para conversar com o agente.

Uso:
    python -m emporio                    # nova conversa
    python -m emporio --sessao ana       # cria/retoma a conversa "ana" (histórico persistido)
    python -m emporio --debug            # mostra as ferramentas chamadas
"""

from __future__ import annotations

import argparse
import json
import sys

from .agent import Agent, ToolCall

DIM, BOLD, CYAN, GREEN, RESET = "\033[2m", "\033[1m", "\033[36m", "\033[32m", "\033[0m"
if not sys.stdout.isatty():
    DIM = BOLD = CYAN = GREEN = RESET = ""

HELP = "Comandos: /nova (limpa a conversa)  /debug (liga/desliga ferramentas)  /sair"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Tom — assistente virtual da Empório da Música")
    parser.add_argument("--sessao", help="id da sessão para retomar o histórico")
    parser.add_argument("--modelo", help="modelo Gemini (padrão: GEMINI_MODEL ou gemini-3.5-flash)")
    parser.add_argument("--debug", action="store_true", help="mostra chamadas de ferramentas")
    args = parser.parse_args(argv)

    state = {"debug": args.debug}

    def show_tool(call: ToolCall) -> None:
        if state["debug"]:
            a = json.dumps(call.args, ensure_ascii=False)
            r = json.dumps(call.result, ensure_ascii=False)
            print(f"{DIM}  ⚙ {call.name}({a}) → {r[:300]}{'…' if len(r) > 300 else ''}{RESET}")

    try:
        agent = Agent(session_id=args.sessao, model=args.modelo, on_tool=show_tool)
    except RuntimeError as e:
        sys.exit(str(e))

    print(f"{BOLD}🎸 Empório da Música — atendimento virtual{RESET}")
    print(f"{DIM}sessão: {agent.session_id} · modelo: {agent.model} · {HELP}{RESET}")
    if agent.history:
        print(f"{DIM}(conversa retomada: {len(agent.history)} mensagens no histórico){RESET}")
    print()

    while True:
        try:
            msg = input(f"{CYAN}Você:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg:
            continue
        if msg in {"/sair", "/exit", "/quit"}:
            break
        if msg == "/nova":
            agent.reset()
            print(f"{DIM}(conversa reiniciada){RESET}\n")
            continue
        if msg == "/debug":
            state["debug"] = not state["debug"]
            print(f"{DIM}(debug {'ligado' if state['debug'] else 'desligado'}){RESET}\n")
            continue
        try:
            turn = agent.send(msg)
        except Exception as e:  # erro de rede/API: avisa e continua
            print(f"{DIM}[erro ao falar com o modelo: {e}]{RESET}\n")
            continue
        print(f"{GREEN}Tom:{RESET} {turn.reply}\n")

    print(f"{DIM}Até mais! Para retomar: python -m emporio --sessao {agent.session_id}{RESET}")


if __name__ == "__main__":
    main()
