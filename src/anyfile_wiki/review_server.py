from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import json
import secrets
import threading

from .assets import apply_review_outputs_for_run
from .decisions import (
    build_decision_actions,
    load_review_decisions,
    write_decision_plan_md,
    write_decisions_summary_md,
    write_next_actions_jsonl,
)
from .review_ui import render_human_review_html


def load_review_items(path: str | Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                items.append(payload)
    return items


def write_review_decisions_from_records(records: list[dict[str, Any]], review_dir: str | Path) -> dict[str, str]:
    root = Path(review_dir)
    root.mkdir(parents=True, exist_ok=True)
    decisions_path = root / "review-decisions.jsonl"
    summary_path = root / "decisions-summary.md"
    actions_path = root / "next-actions.jsonl"
    plan_path = root / "decision-plan.md"

    lines = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records]
    decisions_path.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""), encoding="utf-8")
    decisions = load_review_decisions(decisions_path)
    actions = build_decision_actions(decisions)
    write_decisions_summary_md(decisions, summary_path)
    write_next_actions_jsonl(actions, actions_path)
    write_decision_plan_md(actions, plan_path)
    outputs = {
        "review_decisions": str(decisions_path),
        "decisions_summary": str(summary_path),
        "next_actions": str(actions_path),
        "decision_plan": str(plan_path),
    }
    outputs.update(apply_review_outputs_for_run(root))
    return outputs


def make_review_server(
    *,
    review_dir: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
    once: bool = False,
) -> tuple[ThreadingHTTPServer, str]:
    root = Path(review_dir)
    review_jsonl = root / "human-review.jsonl"
    if not review_jsonl.exists():
        raise FileNotFoundError(f"human-review.jsonl not found: {review_jsonl}")
    server_token = token or secrets.token_urlsafe(18)
    submit_path = f"/api/decisions?token={server_token}"
    page_html = render_human_review_html(
        load_review_items(review_jsonl),
        source_path=review_jsonl,
        server_mode=True,
        submit_url=submit_path,
    ).encode("utf-8")

    class ReviewHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature.
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook.
            parsed = urlparse(self.path)
            if parsed.path not in {"/", "/review"}:
                self._send_json({"ok": False, "error": "not found"}, status=404)
                return
            if not self._authorized(parsed):
                self._send_json({"ok": False, "error": "unauthorized"}, status=403)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page_html)))
            self.end_headers()
            self.wfile.write(page_html)

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook.
            parsed = urlparse(self.path)
            if parsed.path != "/api/decisions":
                self._send_json({"ok": False, "error": "not found"}, status=404)
                return
            if not self._authorized(parsed):
                self._send_json({"ok": False, "error": "unauthorized"}, status=403)
                return
            try:
                payload = self._read_json()
                records = payload.get("records")
                if not isinstance(records, list) or not records:
                    raise ValueError("records must be a non-empty list")
                outputs = write_review_decisions_from_records(records, root)
            except Exception as exc:  # noqa: BLE001 - return error to browser.
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "outputs": outputs})
            if once and bool(payload.get("final")):
                threading.Thread(target=self.server.shutdown, daemon=True).start()

        def _authorized(self, parsed) -> bool:
            query = parse_qs(parsed.query)
            return query.get("token", [""])[0] == server_token

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer((host, int(port)), ReviewHandler)
    return httpd, server_token
