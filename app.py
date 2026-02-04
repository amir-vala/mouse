from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask import Flask, jsonify, render_template_string, request

APP_ROOT = Path(__file__).resolve().parent
DEFAULT_SCAN_ROOT = Path(os.environ.get("GIT_SCAN_ROOT", APP_ROOT)).resolve()

app = Flask(__name__, static_folder="static")

INDEX_TEMPLATE = """
<!doctype html>
<html lang="fa" dir="rtl">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Git Tree Explorer</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <header class="app-header">
      <div class="title-block">
        <h1>نمایش درختی تاریخچه گیت</h1>
        <p>پوشه مورد نظر را انتخاب کنید تا ریپوهای گیت پیدا شوند و نمودار درختی هر پروژه نمایش داده شود.</p>
      </div>
      <form id="scan-form" class="scan-form">
        <label for="root">مسیر پوشه</label>
        <input id="root" name="root" type="text" placeholder="/path/to/workspace" />
        <button type="submit">اسکن</button>
      </form>
    </header>

    <main>
      <section id="status" class="status"></section>
      <section id="repo-container" class="repo-container"></section>
    </main>

    <div id="tooltip" class="tooltip" role="tooltip" aria-hidden="true"></div>

    <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
    <script src="/static/app.js"></script>
  </body>
</html>
"""


@dataclass
class CommitNode:
    commit_id: str
    parents: List[str]
    author: str
    date: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "id": self.commit_id,
            "short": self.commit_id[:7],
            "parents": self.parents,
            "author": self.author,
            "date": self.date,
            "message": self.message,
        }


def find_git_repos(root: Path) -> List[Path]:
    repos: List[Path] = []
    for current_root, dirnames, _ in os.walk(root):
        if ".git" in dirnames:
            repos.append(Path(current_root))
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__"}]
    return repos


def parse_git_log(repo_path: Path, max_commits: int = 250) -> List[CommitNode]:
    format_token = "%H%x1f%P%x1f%an%x1f%ad%x1f%s%x1e"
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "log",
        f"--max-count={max_commits}",
        "--date=iso",
        f"--pretty=format:{format_token}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    entries = result.stdout.strip("\n\x1e").split("\x1e")
    commits: List[CommitNode] = []
    for entry in entries:
        if not entry.strip():
            continue
        parts = entry.strip().split("\x1f")
        if len(parts) != 5:
            continue
        commit_id, parents_raw, author, date_raw, message = parts
        parents = [p for p in parents_raw.split() if p]
        try:
            parsed_date = datetime.fromisoformat(date_raw.strip())
            date = parsed_date.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            date = date_raw.strip()
        commits.append(
            CommitNode(
                commit_id=commit_id,
                parents=parents,
                author=author.strip(),
                date=date,
                message=message.strip(),
            )
        )
    return commits


def build_tree(commits: List[CommitNode]) -> Dict[str, object]:
    nodes = {commit.commit_id: commit.as_dict() for commit in commits}
    children_map: Dict[str, List[Dict[str, object]]] = {commit_id: [] for commit_id in nodes}
    roots: List[str] = []
    merge_links: List[Dict[str, str]] = []

    for commit in commits:
        if not commit.parents:
            roots.append(commit.commit_id)
            continue
        primary_parent = commit.parents[0]
        if primary_parent in children_map:
            children_map[primary_parent].append(nodes[commit.commit_id])
        else:
            roots.append(commit.commit_id)
        if len(commit.parents) > 1:
            for merge_parent in commit.parents[1:]:
                merge_links.append({"source": merge_parent, "target": commit.commit_id})

    def attach_children(node: Dict[str, object]) -> Dict[str, object]:
        node_id = node["id"]
        children = [attach_children(child) for child in children_map.get(node_id, [])]
        if children:
            node["children"] = children
        return node

    root_nodes = [attach_children(nodes[root_id]) for root_id in roots]
    if len(root_nodes) == 1:
        tree = root_nodes[0]
    else:
        tree = {
            "id": "root",
            "short": "root",
            "author": "",
            "date": "",
            "message": "ریشه چند شاخه",
            "parents": [],
            "children": root_nodes,
        }

    return {"tree": tree, "merge_links": merge_links}


@app.route("/")
def index() -> str:
    return render_template_string(INDEX_TEMPLATE)


@app.route("/api/repos")
def api_repos():
    root_param = request.args.get("root")
    root_path = Path(root_param).expanduser().resolve() if root_param else DEFAULT_SCAN_ROOT
    if not root_path.exists():
        return jsonify({"error": "مسیر وارد شده وجود ندارد.", "repos": []}), 400
    repos = []
    for repo_path in find_git_repos(root_path):
        commits = parse_git_log(repo_path)
        tree_payload = build_tree(commits) if commits else {"tree": None, "merge_links": []}
        repos.append(
            {
                "name": repo_path.name,
                "path": str(repo_path),
                "commit_count": len(commits),
                **tree_payload,
            }
        )
    return jsonify({"root": str(root_path), "repos": repos})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
