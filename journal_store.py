"""Shared GitHub-backed paper journal. One writer (scheduled robot), many readers.

The GitHub repository must be private if trading history is considered sensitive.
The Streamlit app needs a read-only GitHub token in secrets; the Actions job uses
GITHUB_TOKEN with contents:write. No local fallback is permitted in production.
"""
import base64
import json
import os
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

JOURNAL_PATH = "data/aktieradar6_journal.json"
BRANCH = os.getenv("AKTIERADAR_JOURNAL_BRANCH", "aktieradar-6.0")
EMPTY = {"version": 1, "events": [], "trades": []}


def _config():
    repo = os.getenv("AKTIERADAR_JOURNAL_REPO") or os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("AKTIERADAR_JOURNAL_TOKEN") or os.getenv("GH_TOKEN")
    if not repo or "/" not in repo:
        raise RuntimeError("Gemensam journal kräver GitHub-repo")
    return repo, token


def _request(method, url, token, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=body, method=method, headers={
        **({"Authorization": "Bearer " + token} if token else {}),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AktieRadar-6.0-Journal",
        **({"Content-Type": "application/json"} if body is not None else {}),
    })
    try:
        with urlopen(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404 and method == "GET":
            return None
        raise RuntimeError("Journalens GitHub-API gav HTTP " + str(exc.code)) from None


def read_shared():
    repo, token = _config()
    url = f"https://api.github.com/repos/{repo}/contents/{JOURNAL_PATH}?ref={quote(BRANCH)}"
    result = _request("GET", url, token)
    if result is None:
        return dict(EMPTY, events=[], trades=[]), None
    raw = base64.b64decode(result["content"]).decode("utf-8")
    data = json.loads(raw)
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("events"), list)
            or not isinstance(data.get("trades"), list)):
        raise RuntimeError("Gemensamma journalen har ogiltigt format")
    return data, result["sha"]


def write_shared(data, sha):
    repo, token = _config()
    if data.get("version") != 1 or not isinstance(data.get("trades"), list):
        raise ValueError("Ogiltig journal")
    url = f"https://api.github.com/repos/{repo}/contents/{JOURNAL_PATH}"
    content = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    payload = {"message": "Update AktieRadar 6.0 paper-trading journal",
               "content": content, "branch": BRANCH}
    if sha:
        payload["sha"] = sha
    _request("PUT", url, token, payload)


def read_public_snapshot():
    """Read public journal from raw.githubusercontent.com, without GitHub API quota.

    For the read-only Streamlit dashboard only; scheduled writer uses read_shared
    with GitHub SHA and token so optimistic locking remains intact.
    """
    repo = os.getenv("AKTIERADAR_JOURNAL_REPO") or "anderssonjesper3-lgtm/AktieRadar-AI"
    if repo != "anderssonjesper3-lgtm/AktieRadar-AI":
        raise RuntimeError("Okänt publikt journalarkiv")
    url = f"https://raw.githubusercontent.com/{repo}/{quote(BRANCH)}/{JOURNAL_PATH}"
    request = Request(url, headers={"User-Agent": "AktieRadar-6.0-ReadOnly"})
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Publika journalen kunde inte läsas (HTTP {exc.code})") from None
    if (not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("events"), list)
            or not isinstance(data.get("trades"), list)):
        raise RuntimeError("Publika journalen har ogiltigt format")
    return data
