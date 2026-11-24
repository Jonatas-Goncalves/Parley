from __future__ import annotations

import ast
from pathlib import Path

WELCOME = Path(__file__).resolve().parents[1] / "src" / "parley" / "ui" / "pages" / "welcome.py"


def _constants() -> dict[str, object]:
    tree = ast.parse(WELCOME.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = ast.literal_eval(node.value)
    return values


def test_welcome_order_puts_japanese_before_korean_and_chinese_last() -> None:
    assert _constants()["ORDER"] == ("pt", "en", "es", "fr", "it", "ja", "ko", "zh")


def test_welcome_translates_the_cjk_language_buttons() -> None:
    assert _constants()["TRANSLATED_LANGUAGES"] == {
        "ja": "language_ja",
        "ko": "language_ko",
        "zh": "language_zh",
    }
