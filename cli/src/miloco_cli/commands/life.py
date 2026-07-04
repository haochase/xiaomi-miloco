"""life command group for demo-first outfit and cooking flows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from miloco_cli.client import api_get, api_post
from miloco_cli.output import print_result


def _builtin_mimo_payload() -> dict[str, Any]:
    return {
        "source_id": "demo_afternoon_interview_dinner",
        "caption": "mock MiMo extraction for an interview outfit and dinner plan",
        "wardrobe": [
            {
                "id": "wardrobe_blazer_gray",
                "name": "dark gray blazer",
                "category": "outerwear",
                "colors": ["dark gray"],
                "season_tags": ["spring", "autumn"],
                "style_tags": ["business", "stable"],
                "formality": 4,
                "warmth_level": 3,
                "confidence": 0.93,
            },
            {
                "id": "wardrobe_shirt_white",
                "name": "white shirt",
                "category": "top",
                "colors": ["white"],
                "season_tags": ["spring", "summer", "autumn"],
                "style_tags": ["simple", "business"],
                "formality": 4,
                "warmth_level": 2,
                "confidence": 0.92,
            },
            {
                "id": "wardrobe_trousers_black",
                "name": "black trousers",
                "category": "bottom",
                "colors": ["black"],
                "season_tags": ["spring", "autumn", "winter"],
                "style_tags": ["simple", "stable"],
                "formality": 4,
                "warmth_level": 3,
                "confidence": 0.9,
            },
        ],
        "pantry": [
            {
                "id": "pantry_eggs",
                "name": "eggs",
                "category": "protein",
                "storage": "fridge",
                "freshness": "fresh",
                "diet_tags": ["light"],
                "confidence": 0.95,
            },
            {
                "id": "pantry_tomatoes",
                "name": "tomatoes",
                "category": "vegetable",
                "storage": "fridge",
                "freshness": "use_soon",
                "diet_tags": ["light"],
                "confidence": 0.9,
            },
            {
                "id": "pantry_greens",
                "name": "greens",
                "category": "vegetable",
                "storage": "fridge",
                "freshness": "fresh",
                "diet_tags": ["light"],
                "confidence": 0.86,
            },
            {
                "id": "pantry_dumplings",
                "name": "frozen dumplings",
                "category": "staple",
                "storage": "freezer",
                "freshness": "normal",
                "diet_tags": ["quick"],
                "confidence": 0.88,
            },
        ],
        "preferences": [
            {
                "id": "pref_outfit_interview",
                "domain": "outfit",
                "person_id": "demo_user",
                "tags": ["not flashy", "business casual", "stable colors"],
                "confidence": 0.9,
            },
            {
                "id": "pref_cooking_family",
                "domain": "cooking",
                "tags": ["light", "not too salty", "quick dinner"],
                "confidence": 0.9,
            },
        ],
        "low_confidence_notes": ["Accessory color was not clear in the mock image."],
    }


def _load_fixture(path: str | None) -> dict[str, Any]:
    if path is None:
        return _builtin_mimo_payload()
    fixture_path = Path(path)
    try:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise click.ClickException(f"cannot read fixture: {fixture_path}") from exc
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"fixture is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise click.ClickException("fixture must contain a JSON object")
    return data


@click.group("life")
def life_group():
    """Life-agent demo commands for outfit, cooking, and notify seams."""


@life_group.command("demo")
@click.option(
    "--fixture",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Mock MiMo JSON fixture. Omit to use the built-in desensitized demo case.",
)
@click.option("--occasion", default="tomorrow morning interview", show_default=True)
@click.option("--weather", default="cool and cloudy", show_default=True)
@click.option(
    "--people-count", default=3, show_default=True, type=click.IntRange(1, 12)
)
@click.option(
    "--time-budget-minutes",
    default=30,
    show_default=True,
    type=click.IntRange(5, 240),
)
@click.option(
    "--persist",
    is_flag=True,
    default=False,
    help="Ask the backend to persist extracted assets and recommendation history.",
)
@click.option(
    "--db-path",
    default=None,
    help="Backend-local SQLite path used when --persist is enabled.",
)
@click.option("--pretty", is_flag=True)
def life_demo(
    fixture,
    occasion,
    weather,
    people_count,
    time_budget_minutes,
    persist,
    db_path,
    pretty,
):
    """Run mock MiMo payload through backend life recommendations."""
    body = {
        "mimo_payload": _load_fixture(fixture),
        "occasion": occasion,
        "weather": weather,
        "people_count": people_count,
        "time_budget_minutes": time_budget_minutes,
        "persist": persist,
    }
    if db_path:
        body["db_path"] = db_path
    data = api_post("/api/life/demo", body)
    print_result(data, pretty)


@life_group.command("history")
@click.option(
    "--db-path",
    default="data/life-demo.db",
    show_default=True,
    help="Backend-local SQLite path that stores life recommendation history.",
)
@click.option(
    "--domain",
    default=None,
    type=click.Choice(["outfit", "cooking"], case_sensitive=False),
    help="Limit history to one life domain.",
)
@click.option(
    "--source-id",
    default=None,
    help="Limit history to recommendations recorded for one MiMo source id.",
)
@click.option("--limit", default=10, show_default=True, type=click.IntRange(1, 100))
@click.option("--pretty", is_flag=True)
def life_history(db_path, domain, source_id, limit, pretty):
    """Read persisted life recommendation history from the backend."""
    params = {
        "db_path": db_path,
        "limit": limit,
    }
    if domain:
        params["domain"] = domain.lower()
    if source_id:
        params["source_id"] = source_id
    data = api_get("/api/life/history", params=params)
    print_result(data, pretty)


@life_group.command("trigger")
@click.option(
    "--trigger-source",
    required=True,
    type=click.Choice(["manual", "voice_intent", "schedule"], case_sensitive=False),
    help="Explicit on-demand source that requested this life-agent run.",
)
@click.option(
    "--domain",
    required=True,
    type=click.Choice(["outfit", "cooking"], case_sensitive=False),
)
@click.option("--source-id", default=None)
@click.option("--occasion", default="today outing", show_default=True)
@click.option("--weather", default=None)
@click.option(
    "--people-count", default=1, show_default=True, type=click.IntRange(1, 12)
)
@click.option(
    "--time-budget-minutes",
    default=30,
    show_default=True,
    type=click.IntRange(1, 240),
)
@click.option(
    "--db-path",
    default="data/life-demo.db",
    show_default=True,
    help="Backend-local SQLite path used for inventory and recommendation history.",
)
@click.option(
    "--persist/--no-persist",
    default=True,
    show_default=True,
    help="Persist the recommendation history for this explicit trigger.",
)
@click.option("--pretty", is_flag=True)
def life_trigger(
    trigger_source,
    domain,
    source_id,
    occasion,
    weather,
    people_count,
    time_budget_minutes,
    db_path,
    persist,
    pretty,
):
    """Run one life-agent recommendation without attaching to realtime perception."""
    body = {
        "trigger_source": trigger_source.lower(),
        "domain": domain.lower(),
        "occasion": occasion,
        "weather": weather,
        "people_count": people_count,
        "time_budget_minutes": time_budget_minutes,
        "persist": persist,
        "db_path": db_path,
    }
    if source_id:
        body["source_id"] = source_id
    data = api_post("/api/life/trigger", body)
    print_result(data, pretty)


@life_group.command("text-trigger")
@click.option("--text", required=True, help="Speech transcript or command text.")
@click.option(
    "--trigger-source",
    default="voice_intent",
    show_default=True,
    type=click.Choice(["manual", "voice_intent", "schedule"], case_sensitive=False),
)
@click.option("--source-id", default=None)
@click.option("--occasion", default="today outing", show_default=True)
@click.option("--weather", default=None)
@click.option(
    "--people-count", default=1, show_default=True, type=click.IntRange(1, 12)
)
@click.option(
    "--time-budget-minutes",
    default=30,
    show_default=True,
    type=click.IntRange(1, 240),
)
@click.option(
    "--db-path",
    default="data/life-demo.db",
    show_default=True,
    help="Backend-local SQLite path used for inventory and recommendation history.",
)
@click.option(
    "--persist/--no-persist",
    default=True,
    show_default=True,
    help="Persist the recommendation history if the text command triggers an agent.",
)
@click.option("--pretty", is_flag=True)
def life_text_trigger(
    text,
    trigger_source,
    source_id,
    occasion,
    weather,
    people_count,
    time_budget_minutes,
    db_path,
    persist,
    pretty,
):
    """Classify command text and run a life-agent trigger when matched."""
    body = {
        "text": text,
        "trigger_source": trigger_source.lower(),
        "occasion": occasion,
        "weather": weather,
        "people_count": people_count,
        "time_budget_minutes": time_budget_minutes,
        "persist": persist,
        "db_path": db_path,
    }
    if source_id:
        body["source_id"] = source_id
    data = api_post("/api/life/trigger", body)
    print_result(data, pretty)


@life_group.command("notify")
@click.option("--message", required=True, help="Life-agent notification text.")
@click.option(
    "--domain",
    required=True,
    type=click.Choice(["outfit", "cooking"], case_sensitive=False),
)
@click.option(
    "--urgency",
    default="low",
    show_default=True,
    type=click.Choice(["low", "medium", "high"], case_sensitive=False),
)
@click.option("--requires-ack", is_flag=True, default=False)
@click.option("--pc-speaker-url", default=None)
@click.option(
    "--fallback-to-text/--no-fallback-to-text", default=True, show_default=True
)
@click.option("--pretty", is_flag=True)
def life_notify(
    message,
    domain,
    urgency,
    requires_ack,
    pc_speaker_url,
    fallback_to_text,
    pretty,
):
    """Send a life-agent notification through backend text/PC speaker fallback."""
    body = {
        "message": message,
        "domain": domain.lower(),
        "urgency": urgency.lower(),
        "requires_ack": requires_ack,
        "fallback_to_text": fallback_to_text,
    }
    if pc_speaker_url:
        body["pc_speaker_url"] = pc_speaker_url
    data = api_post("/api/life/notify", body)
    print_result(data, pretty)
