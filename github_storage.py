from __future__ import annotations

import base64
from io import StringIO

import pandas as pd
import requests
import streamlit as st


OWNER = "ORosa10"
REPOSITORY = "ProfessionalDashboard"
BRANCH = "main"
RATINGS_PATH = "data/company_ratings.csv"
API_URL = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/contents/{RATINGS_PATH}"


def github_token() -> str | None:
    try:
        value = st.secrets["github"]["token"]
    except (FileNotFoundError, KeyError, TypeError):
        return None
    return str(value) if value else None


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_ratings(token: str) -> tuple[pd.DataFrame, str | None]:
    response = requests.get(API_URL, headers=_headers(token), params={"ref": BRANCH}, timeout=20)
    if response.status_code == 404:
        return pd.DataFrame(
            columns=["canonical_company_id", "rating", "contact_strength", "notes"]
        ), None
    response.raise_for_status()
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode("utf-8-sig")
    return pd.read_csv(StringIO(content)).fillna(""), payload["sha"]


def save_ratings(token: str, ratings: pd.DataFrame, sha: str | None) -> None:
    csv_bytes = ratings.to_csv(index=False).encode("utf-8-sig")
    payload: dict[str, str] = {
        "message": "Update company ratings from Streamlit",
        "content": base64.b64encode(csv_bytes).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    response = requests.put(API_URL, headers=_headers(token), json=payload, timeout=20)
    response.raise_for_status()
