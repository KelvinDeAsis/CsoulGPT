"""Stream English conversation from a local Ollama model."""

from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path
import os
import re
from shutil import which
import sys


DEFAULT_MODEL = "qwen3.5:4b-q4_K_M"
CONTEXT_LENGTH = 8192
SYSTEM_PROMPT = (
    "You are CsoulGPT, a friendly AI chatbot for casual conversation. "
    "Write every reply in English, including when the user requests another language. "
    "Give just the answer, with no extra offer or follow-up question. "
    "The only exceptions are when the user asks for a question or when you need a detail to do the task. "
    "For small talk, acknowledge what the user said in one or two sentences. "
    "Example: 'I finally finished that book.' Reply: 'Nice. It feels good to finish a book that took a while.' "
    "Example: 'What is 5 plus 3?' Reply: '8.' "
    "Match the requested length and format. Keep earlier constraints and use the latest correction. "
    "If you don't know something, say so. Don't invent facts, memories, or personal experiences."
)
CONTINUE_PROMPT = "Continue your last answer from where it was cut off. Do not repeat the part already shown."


class ChatError(Exception):
    """A request could not produce a complete reply."""


class ReplyTruncated(ChatError):
    """Generation stopped at the reply limit."""


def message_cost(message):
    # Allow roughly three letters per token in English words. Keep a byte
    # estimate for other text and reserve room for the model's chat template.
    cost = 32
    for segment in re.findall(r"[A-Za-z]+|[^A-Za-z]+", message["content"]):
        if len(segment) <= 24 and segment.isascii() and segment.isalpha():
            cost += (len(segment) + 2) // 3
        else:
            cost += len(segment.encode("utf-8"))
    return cost


def chat_messages(history, prompt, max_tokens, partial=None):
    system = {"role": "system", "content": SYSTEM_PROMPT}
    latest = [{"role": "user", "content": prompt}]
    if partial is not None:
        latest.extend([
            {"role": "assistant", "content": partial},
            {"role": "user", "content": CONTINUE_PROMPT},
        ])
    remaining = CONTEXT_LENGTH - max_tokens - 384 - message_cost(system)
    remaining -= sum(message_cost(message) for message in latest)
    if remaining < 0:
        raise ChatError("That message is too long for the chat context. Shorten it and try again.")
    start = len(history)
    while start:
        exchange_cost = message_cost(history[start - 2]) + message_cost(history[start - 1])
        if exchange_cost > remaining:
            break
        remaining -= exchange_cost
        start -= 2
    return [system, *history[start:], *latest]


def check_ollama(model):
    connection = HTTPConnection("127.0.0.1", 11434, timeout=4)
    try:
        connection.request("GET", "/api/tags")
        with connection.getresponse() as response:
            if response.status != 200:
                raise ChatError(f"Ollama returned HTTP {response.status}. Restart Ollama and try again.")
            models = json.load(response)["models"]
            names = {entry["name"] for entry in models}
    except ConnectionRefusedError as error:
        installed = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if not which("ollama") and not installed.is_file():
            raise ChatError("Install Ollama for Windows from https://ollama.com/download/windows, then open it.") from error
        raise ChatError("Open Ollama from the Start menu or run 'ollama serve', then try again.") from error
    except (OSError, HTTPException, ValueError, TypeError, KeyError) as error:
        raise ChatError("Could not read the local Ollama model list. Open or restart Ollama, then try again.") from error
    finally:
        connection.close()
    requested_name = model if ":" in model.rsplit("/", 1)[-1] else f"{model}:latest"
    if model not in names and requested_name not in names:
        raise ChatError(f"Model {model} is missing. Run 'ollama pull {model}' in PowerShell, then try again.")


def stream_reply(args, messages):
    body = json.dumps({
        "model": args.model,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": {
            "num_ctx": CONTEXT_LENGTH,
            "num_predict": args.max_tokens,
            "temperature": args.temperature,
        },
    }).encode("utf-8")
    connection = HTTPConnection("127.0.0.1", 11434, timeout=120)
    try:
        connection.request("POST", "/api/chat", body=body, headers={"Content-Type": "application/json"})
        with connection.getresponse() as response:
            if response.status == 404:
                raise ChatError(f"Model {args.model} is unavailable. Run 'ollama pull {args.model}' in PowerShell.")
            if response.status != 200:
                raise ChatError(f"Ollama returned HTTP {response.status}. Check the Ollama server logs.")
            for line in response:
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ChatError("Ollama sent an invalid chat event. Check the Ollama server logs.")
                if event.get("error"):
                    raise ChatError(f"Ollama stopped generation: {event['error']}")
                message = event.get("message", {})
                if not isinstance(message, dict) or not isinstance(message.get("content", ""), str):
                    raise ChatError("Ollama sent invalid reply text. Check the Ollama server logs.")
                if message.get("content"):
                    yield message["content"]
                if event.get("done") is True:
                    if event.get("done_reason") == "length":
                        raise ReplyTruncated("Reply reached the token limit.")
                    return
            raise ChatError("Ollama disconnected before finishing the reply. Try again.")
    except (ValueError, HTTPException) as error:
        raise ChatError("Ollama sent an invalid or incomplete response. Try again.") from error
    except TimeoutError as error:
        raise ChatError("Ollama timed out. Check that the model can load and try again.") from error
    except ConnectionRefusedError as error:
        raise ChatError("Ollama is unavailable. Open the Ollama app or run 'ollama serve' in another terminal.") from error
    except OSError as error:
        raise ChatError("The connection to Ollama failed. Check that it is running and try again.") from error
    finally:
        connection.close()


def chat(args):
    one_shot = args.prompt is not None
    history = []
    pending = None
    if not one_shot:
        print(f"CsoulGPT | {args.model} via Ollama")
        print("Type /continue after a cut-off reply, /reset to clear the conversation, or /exit to quit.")

    while True:
        try:
            prompt = (args.prompt if one_shot else input("You> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        partial = None
        if not one_shot:
            if prompt == "/exit":
                return 0
            if prompt == "/reset":
                history.clear()
                pending = None
                print("Conversation reset.")
                continue
            if prompt == "/continue":
                if pending is None:
                    print("There is no cut-off reply to continue.")
                    continue
                prompt, partial = pending
            if not prompt:
                continue

        chunks = []
        try:
            if not prompt:
                raise ChatError("Enter a nonempty prompt.")
            messages = chat_messages(history, prompt, args.max_tokens, partial)
            for chunk in stream_reply(args, messages):
                if not chunks and not one_shot:
                    print("Bot> ", end="")
                print(chunk, end="", flush=True)
                chunks.append(chunk)
            answer = "".join(chunks).strip()
            if not answer:
                raise ChatError("Ollama returned an empty reply. Try again.")
        except ReplyTruncated:
            if chunks:
                print()
            segment = "".join(chunks).strip()
            if one_shot:
                print("Reply reached the token limit. Rerun with a larger --max-tokens value.", file=sys.stderr)
                return 1
            if segment:
                pending = prompt, f"{partial}\n{segment}" if partial is not None else segment
                print("Reply reached the token limit. Type /continue to keep going.")
            else:
                print("Reply reached the token limit without new text.", file=sys.stderr)
            continue
        except (ChatError, KeyboardInterrupt) as error:
            if chunks:
                print()
            interrupted = isinstance(error, KeyboardInterrupt)
            print("Reply cancelled." if interrupted else error, file=sys.stderr)
            if one_shot:
                return 130 if interrupted else 1
            continue

        print()
        if one_shot:
            return 0
        if partial is not None:
            messages = messages[:-2]
            answer = f"{partial}\n{answer}"
        history = [*messages[1:], {"role": "assistant", "content": answer}]
        pending = None
