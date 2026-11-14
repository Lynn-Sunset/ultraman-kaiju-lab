"""Publish this authorized project through the already signed-in Git account.

Credentials remain in memory, and Git uses its existing credential manager.
No token is written to disk, command arguments, Git configuration, or logs.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OWNER = "Lynn-Sunset"
NAME = "ultraman-kaiju-lab"
API = "https://api.github.com"
STATE = ROOT / ".deploy" / "github.json"
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")


def session():
    result = subprocess.run(["git", "credential", "fill"], input=f"protocol=https\nhost=github.com\nusername={OWNER}\n\n", text=True, capture_output=True, env=ENV, timeout=30)
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    secret = fields.get("password")
    if not secret:
        raise RuntimeError("The expected GitHub account is not signed in.")
    client = requests.Session()
    client.headers.update({"Authorization": f"Bearer {secret}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    response = client.get(API + "/user", timeout=30)
    response.raise_for_status()
    user = response.json()
    if user["login"].lower() != OWNER.lower():
        raise RuntimeError("GitHub account mismatch; no changes made.")
    scopes = response.headers.get("X-OAuth-Scopes", "")
    if "workflow" not in [scope.strip() for scope in scopes.split(",")]:
        raise RuntimeError("The existing GitHub credential does not include workflow permission.")
    return client, user


def git(*arguments):
    result = subprocess.run(["git", *arguments], cwd=ROOT, env=ENV, text=True, capture_output=True, timeout=180)
    if result.returncode:
        # Git command arguments never contain credentials.
        raise RuntimeError(result.stderr.strip() or "Git operation failed.")
    return result.stdout.strip()


def write_state(value):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, indent=2), encoding="utf-8")


def publish(client, user):
    if not (ROOT / "dist" / "index.html").is_file():
        raise RuntimeError("Build and review the Pages artifact before publishing.")
    expected = f"https://github.com/{OWNER}/{NAME}.git"
    result = client.get(f"{API}/repos/{OWNER}/{NAME}", timeout=30)
    if result.status_code == 404:
        response = client.post(API + "/user/repos", json=dict(name=NAME, description="奥特怪兽身份匹配 · 30类怪兽 · 浏览器本地推理 · 红白主题", private=False, auto_init=False, has_issues=True, has_projects=False, has_wiki=False), timeout=30)
        response.raise_for_status()
        repo = response.json()
        write_state(dict(repository_id=repo["id"], repository=repo["html_url"], remote=expected, owner=OWNER, name=NAME))
        print("Created " + repo["html_url"], flush=True)
    else:
        result.raise_for_status()
        repo = result.json()
        if not STATE.exists() or json.loads(STATE.read_text(encoding="utf-8"))["repository_id"] != repo["id"]:
            raise RuntimeError("An existing repository was found without this project's publication state; refusing to overwrite it.")
    if not (ROOT / ".git").exists():
        git("init", "-b", "main")
        git("config", "user.name", OWNER)
        git("config", "user.email", f"{user['id']}+{OWNER}@users.noreply.github.com")
        git("remote", "add", "origin", expected)
    if git("remote", "get-url", "origin") != expected:
        raise RuntimeError("Unexpected Git remote; stopped.")
    if git("branch", "--show-current") != "main":
        raise RuntimeError("Unexpected branch; stopped.")
    tracked = [".github", ".gitignore", "README.md", "package.json", "package-lock.json", "web", "backend", "scripts", "third_party", "tests", "requirements.txt", "requirements-export.txt", "export_browser.py", "train.py", "collect_dataset.py", "expand_dataset.py", "supplement_dataset.py", "supplement_expansion.py", "review_dataset.py", "review_expansion.py", "annotate_seed.py", "summarize_dataset.py", "start.ps1", "data/labels.csv", "data/manifest.json", "data/review-decisions.json", "data/class-summary.csv", "data/summary.json", "data/expansion-review-snapshot.json", "models/monster.report.json"]
    git("add", "--", *tracked)
    staged = git("diff", "--cached", "--name-only")
    if any(part in staged.splitlines() for part in [".env", ".deploy/github.json"]):
        raise RuntimeError("Unexpected local state in staged source; stopped.")
    if staged:
        git("commit", "-m", "Launch red-and-white kaiju matcher with private browser inference")
    git("push", "-u", "origin", "main")
    print("Pushed " + git("rev-parse", "HEAD"), flush=True)
    pages = client.get(f"{API}/repos/{OWNER}/{NAME}/pages", timeout=30)
    if pages.status_code == 404:
        pages = client.post(f"{API}/repos/{OWNER}/{NAME}/pages", json={"build_type": "workflow"}, timeout=30)
        pages.raise_for_status()
    else:
        pages.raise_for_status()
        if pages.json().get("build_type") != "workflow":
            raise RuntimeError("Unexpected existing Pages publishing source; stopped.")
    site = pages.json().get("html_url") or f"https://{OWNER.lower()}.github.io/{NAME}/"
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update(pages_url=site, commit=git("rev-parse", "HEAD"))
    write_state(state)
    print("GitHub Pages configured: " + site, flush=True)


def status(client):
    response = client.get(f"{API}/repos/{OWNER}/{NAME}/actions/runs", params={"per_page": 3}, timeout=30)
    response.raise_for_status()
    runs = response.json()["workflow_runs"]
    print(json.dumps([dict(id=run["id"], status=run["status"], conclusion=run["conclusion"], url=run["html_url"], sha=run["head_sha"]) for run in runs], indent=2), flush=True)
    pages = client.get(f"{API}/repos/{OWNER}/{NAME}/pages", timeout=30)
    if pages.ok:
        print(json.dumps({key: pages.json().get(key) for key in ["html_url", "status", "build_type", "https_enforced"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["publish", "status"])
    args = parser.parse_args()
    client, user = session()
    publish(client, user) if args.action == "publish" else status(client)
