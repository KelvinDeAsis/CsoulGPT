"""Local English conversation through Ollama."""

import argparse
import math
import sys

from local_chat import ChatError, CONTEXT_LENGTH, DEFAULT_MODEL, chat, check_ollama


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    conversation = subcommands.add_parser("chat", help="Chat with a local Ollama model.")
    conversation.add_argument("--prompt")
    browser = subcommands.add_parser("web", help="Open CsoulGPT in a local browser.")
    browser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser.")
    for command in (conversation, browser):
        command.add_argument("--model", default=DEFAULT_MODEL)
        command.add_argument("--temperature", type=float, default=0.7)
        command.add_argument("--max-tokens", type=int, default=512, help="Maximum reply tokens (default: 512).")
        command.add_argument("--check", action="store_true", help="Check whether Ollama and the model are ready.")
    args = parser.parse_args()
    if not args.model.strip():
        parser.error("--model must not be empty")
    if not math.isfinite(args.temperature) or args.temperature < 0:
        parser.error("--temperature must be a finite nonnegative number")
    if not 1 <= args.max_tokens <= CONTEXT_LENGTH - 1024:
        parser.error(f"--max-tokens must be between 1 and {CONTEXT_LENGTH - 1024}")
    if args.check or args.command == "web":
        try:
            check_ollama(args.model)
        except ChatError as error:
            print(error, file=sys.stderr)
            return 1
        if args.check:
            print(f"Ready: {args.model} via Ollama.")
            return 0
        from browser_chat import serve

        return serve(args)
    return chat(args)


if __name__ == "__main__":
    raise SystemExit(main())
