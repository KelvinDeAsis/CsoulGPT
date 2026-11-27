from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from local_chat import (
    ChatError, CONTEXT_LENGTH, CONTINUE_PROMPT, DEFAULT_MODEL, ReplyTruncated,
    chat, chat_messages, check_ollama, stream_reply,
)


def arguments(prompt=None):
    return SimpleNamespace(prompt=prompt, model=DEFAULT_MODEL, max_tokens=256, temperature=0.7)


class LocalChatTests(unittest.TestCase):
    def test_stream_request_and_reply_text(self):
        response = io.BytesIO(
            b'{"message":{"thinking":"hidden","content":"Hello"}}\n'
            b'{"message":{"content":" there!"},"done":true}\n'
        )
        response.status = 200
        connection = Mock(spec=HTTPConnection)
        connection.getresponse.return_value = response
        messages = chat_messages([], "Hi", 256)
        with patch("local_chat.HTTPConnection", return_value=connection) as factory:
            self.assertEqual(list(stream_reply(arguments(), messages)), ["Hello", " there!"])
        factory.assert_called_once_with("127.0.0.1", 11434, timeout=120)
        request = connection.request.call_args
        self.assertEqual(request.args, ("POST", "/api/chat"))
        self.assertEqual(json.loads(request.kwargs["body"]), {
            "model": DEFAULT_MODEL, "messages": messages, "stream": True, "think": False,
            "options": {"num_ctx": CONTEXT_LENGTH, "num_predict": 256, "temperature": 0.7},
        })
        connection.close.assert_called_once()

    def test_failed_streams_return_nonzero_in_single_prompt_mode(self):
        for status, body, expected in [
            (404, b"", "ollama pull"),
            (200, b"invalid json\n", "invalid or incomplete"),
            (200, b'{"error":"model stopped"}\n', "model stopped"),
            (200, b'{"message":{"content":"Partial"}}\n', "before finishing"),
            (200, b'{"message":{"content":"Partial"},"done":true,"done_reason":"length"}\n', "--max-tokens"),
            (200, b'{"done":true}\n', "empty reply"),
        ]:
            with self.subTest(expected=expected):
                response = io.BytesIO(body)
                response.status = status
                error_output = io.StringIO()
                with patch("local_chat.HTTPConnection") as factory, redirect_stderr(error_output), redirect_stdout(io.StringIO()):
                    factory.return_value.getresponse.return_value = response
                    self.assertEqual(chat(arguments("Hi")), 1)
                self.assertIn(expected, error_output.getvalue())

    def test_unavailable_service_and_timeout(self):
        for error, expected in [
            (ConnectionRefusedError(), "Ollama is unavailable"),
            (TimeoutError(), "Ollama timed out"),
        ]:
            with self.subTest(expected=expected), patch("local_chat.HTTPConnection") as factory:
                factory.return_value.request.side_effect = error
                with self.assertRaisesRegex(ChatError, expected):
                    list(stream_reply(arguments(), chat_messages([], "Hi", 256)))

    def test_successful_history_reset_and_recovery_after_partial_reply(self):
        sent = []

        def reply(args, messages):
            sent.append(messages)
            if messages[-1]["content"] == "Fail":
                yield "Partial"
                raise ChatError("Disconnected")
            yield "Complete"

        inputs = ["I'm Sam", "Fail", "What is my name?", "/reset", "New topic", "/exit"]
        with patch("builtins.input", side_effect=inputs), patch("local_chat.stream_reply", side_effect=reply):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(chat(arguments()), 0)
        self.assertEqual([message["content"] for message in sent[2][1:]], [
            "I'm Sam", "Complete", "What is my name?",
        ])
        self.assertEqual(len(sent[3]), 2)

    def test_continuation_can_retry_and_saves_one_completed_exchange(self):
        sent = []

        def reply(args, messages):
            sent.append(messages)
            if len(sent) in (1, 3):
                yield "Part one" if len(sent) == 1 else "Part two"
                raise ReplyTruncated()
            if len(sent) == 2:
                yield "Dropped text"
                raise ChatError("Disconnected")
            yield "Finished"

        inputs = ["Tell a story", "/continue", "/continue", "/continue", "What did you say?", "/reset", "/continue", "/exit"]
        output = io.StringIO()
        with patch("builtins.input", side_effect=inputs), patch("local_chat.stream_reply", side_effect=reply):
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                self.assertEqual(chat(arguments()), 0)
        self.assertIn("Reply reached the token limit.", output.getvalue())
        self.assertIn("There is no cut-off reply to continue.", output.getvalue())
        self.assertEqual(sent[1], sent[2])
        self.assertEqual([item["content"] for item in sent[3][-3:]], [
            "Tell a story", "Part one\nPart two", CONTINUE_PROMPT,
        ])
        self.assertEqual([item["content"] for item in sent[4][1:]], [
            "Tell a story", "Part one\nPart two\nFinished", "What did you say?",
        ])

    def test_context_retains_complete_recent_exchanges(self):
        old_exchange = [
            {"role": "user", "content": "x" * 7000},
            {"role": "assistant", "content": "y" * 1000},
        ]
        recent_exchange = [
            {"role": "user", "content": "I play guitar."},
            {"role": "assistant", "content": "That's a fun hobby."},
        ]
        messages = chat_messages(old_exchange + recent_exchange, "What do I play?", 256)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1:-1], recent_exchange)
        with self.assertRaisesRegex(ChatError, "too long"):
            chat_messages([], "x" * CONTEXT_LENGTH, 256)

    def test_context_keeps_english_history_longer_than_old_byte_budget(self):
        history = [
            {"role": "user", "content": "After school I usually practice piano for an hour. " * 96},
            {"role": "assistant", "content": "Regular practice helps you remember more of the music. " * 96},
        ]
        self.assertEqual(chat_messages(history, "What do I practice?", 256)[1:-1], history)

    def test_readiness_reports_missing_model(self):
        with patch("local_chat.HTTPConnection") as factory:
            for names in (["other"], [DEFAULT_MODEL]):
                response = io.BytesIO(json.dumps({"models": [{"name": name} for name in names]}).encode())
                response.status = 200
                factory.return_value.getresponse.return_value = response
                if DEFAULT_MODEL in names:
                    check_ollama(DEFAULT_MODEL)
                else:
                    with self.assertRaisesRegex(ChatError, "ollama pull"):
                        check_ollama(DEFAULT_MODEL)
            factory.return_value.request.assert_called_with("GET", "/api/tags")
