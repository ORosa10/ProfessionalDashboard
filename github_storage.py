from __future__ import annotations

import base64
from io import StringIO
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st


OWNER = "ORosa10"
REPOSITORY = "ProfessionalDashboard"
BRANCH = "main"
RATINGS_PATH = "data/company_ratings.csv"
API_URL = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/contents/{RATINGS_PATH}"
RATING_COLUMNS = [
    "canonical_company_id",
    "rating",
    "familiarity",
    "contact_strength",
    "relationship_type",
    "reference_notes",
    "notes",
]


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
        return pd.DataFrame(columns=RATING_COLUMNS), None
    response.raise_for_status()
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode("utf-8-sig")
    ratings = pd.read_csv(StringIO(content)).fillna("")
    return ratings.reindex(columns=RATING_COLUMNS, fill_value=""), payload["sha"]


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


def load_csv_file(
    token: str | None,
    repository_path: str,
    columns: list[str],
) -> tuple[pd.DataFrame, str | None]:
    """Load a small app-owned CSV from GitHub, with a local read-only fallback."""
    api_url = (
        f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/contents/"
        f"{quote(repository_path, safe='/')}"
    )
    if token:
        response = requests.get(
            api_url,
            headers=_headers(token),
            params={"ref": BRANCH},
            timeout=20,
        )
        if response.status_code == 404:
            return pd.DataFrame(columns=columns), None
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload["content"]).decode("utf-8-sig")
        frame = pd.read_csv(StringIO(content)).fillna("")
        return frame.reindex(columns=columns, fill_value=""), payload["sha"]

    local_path = Path(__file__).parent / repository_path
    if local_path.exists():
        frame = pd.read_csv(local_path).fillna("")
        return frame.reindex(columns=columns, fill_value=""), None
    return pd.DataFrame(columns=columns), None


def save_csv_file(
    token: str,
    repository_path: str,
    frame: pd.DataFrame,
    sha: str | None,
    message: str,
) -> None:
    """Persist a small app-owned CSV through the GitHub contents API."""
    api_url = (
        f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/contents/"
        f"{quote(repository_path, safe='/')}"
    )
    csv_bytes = frame.to_csv(index=False).encode("utf-8-sig")
    payload: dict[str, str] = {
        "message": message,
        "content": base64.b64encode(csv_bytes).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha
    response = requests.put(
        api_url,
        headers=_headers(token),
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
