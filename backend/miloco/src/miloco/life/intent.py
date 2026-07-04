# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Text intent helpers for on-demand life agents."""

from __future__ import annotations

OUTFIT_INITIAL_TERMS = (
    "\u7a7f\u642d",
    "\u642d\u914d",
    "\u600e\u4e48\u642d",
    "\u8863\u670d",
    "\u4e0a\u8863",
    "\u88e4\u5b50",
    "\u88d9\u5b50",
    "\u978b",
    "\u5916\u5957",
    "\u8fd9\u4ef6",
    "\u7a7f\u4ec0\u4e48",
    "\u886c\u886b",
    "\u7403\u8863",
    "\u77ed\u8896",
    "\u957f\u8896",
    "outfit",
    "clothes",
    "shirt",
)

COOKING_INITIAL_TERMS = (
    "\u505a\u996d",
    "\u505a\u83dc",
    "\u70f9\u996a",
    "\u5403\u4ec0\u4e48",
    "\u98df\u6750",
    "\u51b0\u7bb1",
    "\u53a8\u623f",
    "\u9505",
    "\u83dc\u8c31",
    "\u600e\u4e48\u505a",
    "\u4e0b\u997a\u5b50",
    "\u716e",
    "\u76d0",
    "\u712f\u6c34",
    "\u6c34\u5f00",
    "cooking",
    "cook",
    "fridge",
    "ingredient",
)

VISUAL_REFERENCE_TERMS = (
    "\u8fd9\u4ef6",
    "\u8fd9\u4e2a",
    "\u624b\u91cc",
    "\u62ff\u7740",
    "\u770b\u770b",
    "\u955c\u5934",
    "\u8eab\u4e0a",
    "\u7a7f\u7740",
    "\u6362\u4e86",
    "\u518d\u770b",
    "\u62cd",
    "this",
    "holding",
    "camera",
    "look at",
)

FOLLOWUP_TERMS = (
    "\u8fd8\u6709\u522b\u7684\u5efa\u8bae",
    "\u8fd8\u6709\u5417",
    "\u522b\u7684\u5efa\u8bae",
    "\u518d\u63a8\u8350",
    "\u518d\u8bf4\u8bf4",
    "\u6362\u4e00\u4ef6",
    "\u6362\u4e86",
    "\u518d\u770b\u770b",
)


def normalize_life_text(text: str) -> str:
    return text.strip().lower()


def matched_life_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = normalize_life_text(text)
    return [term for term in terms if term in normalized]


def is_life_voice_candidate(text: str) -> bool:
    """Return True for initial life-agent commands or active-session follow-ups."""
    normalized = normalize_life_text(text)
    return any(
        term in normalized
        for term in (
            *OUTFIT_INITIAL_TERMS,
            *COOKING_INITIAL_TERMS,
            *FOLLOWUP_TERMS,
        )
    )


def infer_life_occasion(text: str, default: str | None = None) -> str:
    """Infer a compact Chinese occasion label from one speech turn."""
    normalized = normalize_life_text(text)
    if "\u8db3\u7403" in normalized or "\u8e22\u7403" in normalized:
        return "\u4eca\u5929\u51fa\u95e8\u8e22\u8db3\u7403"
    if "\u8dd1\u6b65" in normalized:
        return "\u4eca\u5929\u51fa\u95e8\u8dd1\u6b65"
    if "\u5065\u8eab" in normalized:
        return "\u4eca\u5929\u53bb\u5065\u8eab"
    if any(
        term in normalized for term in ("\u89c6\u9891", "\u7ebf\u4e0a", "\u8fdc\u7a0b")
    ) and any(
        term in normalized for term in ("\u4f1a\u8bae", "\u6c9f\u901a", "\u529e\u516c")
    ):
        return "\u4e0b\u5348\u89c6\u9891\u4f1a\u8bae"
    if "\u9762\u8bd5" in normalized:
        return "\u4eca\u5929\u53c2\u52a0\u9762\u8bd5"
    if any(
        term in normalized for term in ("\u5ba2\u6237", "\u89c1\u5ba2\u6237")
    ) and any(
        term in normalized for term in ("\u4f1a\u8bae", "\u5f00\u4f1a", "\u6c9f\u901a")
    ):
        if "\u4e0a\u73ed" in normalized or "\u901a\u52e4" in normalized:
            return "\u4eca\u5929\u901a\u52e4\u540e\u89c1\u5ba2\u6237\u5f00\u4f1a"
        return "\u4eca\u5929\u89c1\u5ba2\u6237\u5f00\u4f1a"
    if ("\u4e0a\u73ed" in normalized or "\u901a\u52e4" in normalized) and any(
        term in normalized
        for term in ("\u665a\u4e0a", "\u4eca\u665a", "\u670b\u53cb", "\u805a\u9910")
    ):
        return "\u4eca\u5929\u901a\u52e4\u540e\u548c\u670b\u53cb\u5403\u996d"
    if "\u4f1a\u8bae" in normalized:
        return "\u4eca\u5929\u53c2\u52a0\u4f1a\u8bae"
    if "\u4e0a\u73ed" in normalized or "\u901a\u52e4" in normalized:
        return "\u4eca\u5929\u4e0a\u73ed\u901a\u52e4"
    if any(
        term in normalized for term in ("\u665a\u4e0a", "\u4eca\u665a", "\u665a\u9910")
    ) and any(
        term in normalized
        for term in ("\u670b\u53cb", "\u5403\u996d", "\u805a\u9910", "\u996d\u5c40")
    ):
        return "\u4eca\u665a\u548c\u670b\u53cb\u5403\u996d"
    if any(
        term in normalized for term in ("\u5403\u996d", "\u805a\u9910", "\u996d\u5c40")
    ):
        return "\u793e\u4ea4\u805a\u9910"
    if "\u7ea6\u4f1a" in normalized:
        return "\u4eca\u5929\u7ea6\u4f1a"
    if "\u5c45\u5bb6" in normalized or "\u5728\u5bb6" in normalized:
        return "\u4eca\u5929\u5c45\u5bb6"
    return default or "\u65e5\u5e38\u51fa\u95e8"


def infer_life_weather(text: str, default: str | None = None) -> str | None:
    """Infer compact weather/context hints from one speech turn."""
    normalized = normalize_life_text(text)
    hints: list[str] = []
    if any(
        term in normalized
        for term in (
            "\u5357\u65b9",
            "\u534e\u5357",
            "\u6df1\u5733",
            "\u5e7f\u5dde",
            "\u6cbf\u6d77",
        )
    ):
        hints.append("\u5357\u65b9")
    if any(
        term in normalized for term in ("\u5317\u65b9", "\u5317\u4eac", "\u534e\u5317")
    ):
        hints.append("\u5317\u65b9")
    if any(
        term in normalized
        for term in (
            "\u6c5f\u5357",
            "\u4e0a\u6d77",
            "\u676d\u5dde",
            "\u82cf\u5dde",
        )
    ):
        hints.append("\u6c5f\u5357")
    if any(term in normalized for term in ("\u590f\u5929", "\u590f\u5b63")):
        hints.append("\u590f\u5929")
    if any(term in normalized for term in ("\u79cb\u5929", "\u79cb\u5b63")):
        hints.append("\u79cb\u5929")
    if any(term in normalized for term in ("\u51ac\u5929", "\u51ac\u5b63")):
        hints.append("\u51ac\u5929")
    if any(
        term in normalized
        for term in ("\u4e0b\u96e8", "\u96e8\u5929", "\u6709\u96e8", "\u9635\u96e8")
    ):
        hints.append("\u6709\u96e8")
    if "\u6885\u96e8" in normalized:
        hints.append("\u6885\u96e8\u5b63")
    if any(
        term in normalized
        for term in ("\u5929\u6c14\u4e0d\u597d", "\u9634\u5929", "\u591a\u4e91")
    ):
        hints.append("\u5929\u6c14\u4e0d\u597d")
    if any(
        term in normalized for term in ("\u95f7\u70ed", "\u6e7f\u70ed", "\u6f6e\u6e7f")
    ):
        hints.append("\u95f7\u70ed\u6f6e\u6e7f")
    elif any(term in normalized for term in ("\u70ed", "\u9ad8\u6e29", "\u708e\u70ed")):
        hints.append("\u9ad8\u6e29")
    if any(
        term in normalized
        for term in (
            "\u51b7",
            "\u504f\u51c9",
            "\u5929\u51c9",
            "\u6709\u70b9\u51c9",
            "\u6e7f\u51b7",
            "\u9634\u51b7",
            "\u964d\u6e29",
        )
    ):
        hints.append("\u504f\u51c9")
    if "\u6e7f\u51b7" in normalized:
        hints.append("\u6e7f\u51b7")
    if any(
        term in normalized for term in ("\u5927\u98ce", "\u522e\u98ce", "\u6709\u98ce")
    ):
        hints.append("\u6709\u98ce")
    if any(
        term in normalized
        for term in ("\u5ba4\u5185", "\u7a7a\u8c03", "\u529e\u516c\u5ba4")
    ):
        hints.append("\u5ba4\u5185")
    if hints:
        return "\u3001".join(dict.fromkeys(hints))
    return default
