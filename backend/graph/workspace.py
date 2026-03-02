"""Workspace manifest: lightweight index of all processes in a workspace."""
from __future__ import annotations

import copy
import json


class WorkspaceManifest:
    """Wraps the workspace JSON document (process tree, tags, summaries)."""

    def __init__(self, data: dict):
        self.data = data

    # -- properties --------------------------------------------------------

    @property
    def process_tree(self) -> dict:
        return self.data.get("process_tree", {})

    @property
    def root_id(self) -> str:
        return self.process_tree.get("root", "")

    # -- lookups -----------------------------------------------------------

    def get_process_info(self, process_id: str) -> dict | None:
        return self.process_tree.get("processes", {}).get(process_id)

    def get_children(self, process_id: str) -> list[str]:
        info = self.get_process_info(process_id)
        return list(info.get("children", [])) if info else []

    def get_path(self, process_id: str) -> str:
        info = self.get_process_info(process_id)
        return info.get("path", "") if info else ""

    def all_process_ids(self) -> list[str]:
        return list(self.process_tree.get("processes", {}).keys())

    # -- mutations ---------------------------------------------------------

    def update_summary(self, process_id: str, summary: dict) -> None:
        info = self.get_process_info(process_id)
        if info is not None:
            info["summary"] = summary

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return self.data

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> WorkspaceManifest:
        return cls(json.loads(json_str))

    @classmethod
    def from_dict(cls, d: dict) -> WorkspaceManifest:
        return cls(d)

    def copy(self) -> WorkspaceManifest:
        return WorkspaceManifest(copy.deepcopy(self.data))
