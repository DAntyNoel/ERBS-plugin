from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "erbs_plugin"
FORBIDDEN_MODULES = {"kanamibot", "nonebot", "onebot"}
FORBIDDEN_DOCUMENT_TEXT = ("kanamibot", "nonebot", "onebot", "/users/main/desktop")


def test_package_has_no_consumer_framework_imports() -> None:
    violations: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.split(".", 1)[0].casefold() in FORBIDDEN_MODULES:
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
    assert violations == []


def test_repository_docs_are_consumer_neutral() -> None:
    paths = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    violations: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8").casefold()
        for forbidden in FORBIDDEN_DOCUMENT_TEXT:
            if forbidden in text:
                violations.append(f"{path.relative_to(ROOT)} contains {forbidden}")
    assert violations == []
