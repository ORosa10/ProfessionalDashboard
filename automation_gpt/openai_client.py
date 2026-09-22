#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimální klient OpenAI Responses API pro náborové GitHub Actions (svět bez
Claude). Nahrazuje "inteligenci", kterou dřív dělal Claude v Coworku.

- API klíč se čte z prostředí `OPENAI_API_KEY` (v GitHub Actions ze
  `secrets.OPENAI_API_KEY`). Když chybí, skript se ZASTAVÍ a řekne to — žádná
  tichá náhrada (dle ducha CLAUDE.md projektu).
- Model přes `OPENAI_MODEL` (default "gpt-4o").
- Volitelně web search tool (Responses API `web_search_preview`).

Použití:
    from openai_client import ask, ask_json
    text = ask("prompt", web_search=True)
    data = ask_json("prompt vracející JSON", web_search=True)
"""
import json
import os
import sys
import time

import requests

API_URL = "https://api.openai.com/v1/responses"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")


def _key():
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        sys.exit(
            "CHYBA: chybí OPENAI_API_KEY (přidej ho do GitHub -> Settings -> "
            "Secrets and variables -> Actions). Bez klíče úloha neběží - "
            "žádná tichá náhrada."
        )
    return k


def ask(prompt, web_search=False, max_output_tokens=4000, retries=2):
    """Zavolá model a vrátí čistý text odpovědi."""
    body = {
        "model": MODEL,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }
    if web_search:
        body["tools"] = [{"type": "web_search_preview"}]
    headers = {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
    }
    last = None
    for attempt in range(retries + 1):
        r = requests.post(API_URL, headers=headers, json=body, timeout=180)
        if r.status_code == 200:
            return _extract_text(r.json())
        last = f"HTTP {r.status_code}: {r.text[:500]}"
        if r.status_code in (429, 500, 502, 503):
            time.sleep(5 * (attempt + 1))
            continue
        break
    sys.exit(f"CHYBA volání OpenAI API: {last}")


def ask_json(prompt, web_search=False, max_output_tokens=4000):
    """Jako ask(), ale očekává JSON a vrátí ho jako Python objekt."""
    txt = ask(
        prompt + "\n\nOdpověz VÝHRADNĚ platným JSON, bez markdownu a bez komentářů.",
        web_search=web_search,
        max_output_tokens=max_output_tokens,
    )
    txt = txt.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt.split("\n", 1)[1] if "\n" in txt else txt
        if txt.lstrip().startswith("json"):
            txt = txt.lstrip()[4:]
    start = txt.find("[") if "[" in txt else txt.find("{")
    end = max(txt.rfind("]"), txt.rfind("}"))
    if start == -1 or end == -1:
        sys.exit(f"CHYBA: odpověď modelu není JSON:\n{txt[:500]}")
    return json.loads(txt[start:end + 1])


def _extract_text(resp):
    """Vytáhne text z Responses API payloadu (raw HTTP, bez SDK)."""
    if isinstance(resp.get("output_text"), str) and resp["output_text"].strip():
        return resp["output_text"]
    parts = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text") and c.get("text"):
                    parts.append(c["text"])
    if not parts:
        sys.exit(f"CHYBA: v odpovědi OpenAI není text:\n{json.dumps(resp)[:500]}")
    return "\n".join(parts)
