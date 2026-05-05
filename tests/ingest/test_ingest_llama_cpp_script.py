from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

from continuity.ingest.scripts.llama_cpp_extract import call_llama_cpp_chat, main


class _Handler(BaseHTTPRequestHandler):
    requests: ClassVar[list[dict[str, object]]] = []

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests.append(payload)
        body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": '[{"kind":"project_convention","title":"Local only","summary":"Use local llama.cpp."}]'
                        }
                    }
                ]
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _server() -> tuple[HTTPServer, str]:
    _Handler.requests = []
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/v1/chat/completions"


def test_call_llama_cpp_chat_posts_openai_compatible_payload() -> None:
    server, endpoint = _server()
    try:
        content = call_llama_cpp_chat(
            "extract this",
            endpoint=endpoint,
            model="local-test-model",
            temperature=0.1,
            max_tokens=77,
        )
    finally:
        server.shutdown()

    assert "Local only" in content
    payload = _Handler.requests[0]
    assert payload["model"] == "local-test-model"
    assert payload["temperature"] == 0.1
    assert payload["max_tokens"] == 77
    assert payload["stream"] is False
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "extract this"}


def test_llama_cpp_script_main_reads_stdin_and_prints_content(monkeypatch, capsys) -> None:
    server, endpoint = _server()
    monkeypatch.setattr("sys.stdin", _StringStdin("prompt from ingestion"))
    try:
        exit_code = main(["--endpoint", endpoint])
    finally:
        server.shutdown()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Local only" in captured.out


class _StringStdin:
    def __init__(self, value: str) -> None:
        self.value = value

    def read(self) -> str:
        return self.value
