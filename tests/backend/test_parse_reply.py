"""Unit tests for the Lead reply-parsing helper.

Markers the Lead emits are parsed out of raw CLI output so the display_text
shown to the user never contains orchestrator machinery. These tests pin down
the contract so we don't regress when the prompt template evolves.
"""

from __future__ import annotations

from backend.agents.lead import _parse_reply


def test_plain_reply_has_no_markers_set():
    r = _parse_reply("Just a friendly message.", cost=0.01)
    assert r.display_text == "Just a friendly message."
    assert r.brief_ready is False
    assert r.brief_text is None
    assert r.note_queued is None
    assert r.revision_request is None
    assert r.cost_usd == 0.01


def test_brief_block_extracts_body_and_strips_marker():
    raw = (
        "Ok, you're ready.\n\n"
        "BRIEF:\n"
        "A habit tracker web app for solo devs. Manual check-off.\n"
        "Tech: FastAPI + React. No auth for v1.\n"
        "BRIEF_READY"
    )
    r = _parse_reply(raw, cost=0.03)
    assert r.brief_ready is True
    assert r.brief_text is not None
    assert "habit tracker" in r.brief_text
    assert "FastAPI" in r.brief_text
    # User-visible text must NOT include the raw marker block.
    assert "BRIEF:" not in r.display_text
    assert "BRIEF_READY" not in r.display_text
    # But should include the friendly sign-off substitution.
    assert "Launching Stage 1" in r.display_text


def test_brief_without_marker_does_not_set_brief_ready():
    # Lead proposes a brief but user hasn't approved yet — no BRIEF_READY.
    raw = (
        "Here's a proposed brief:\n\n"
        "A habit tracker for solo devs.\n\n"
        "Does this look right, or should we tweak anything?"
    )
    r = _parse_reply(raw, cost=0.02)
    assert r.brief_ready is False
    assert r.brief_text is None
    assert "habit tracker" in r.display_text  # body preserved, no marker stripped


def test_note_queued_marker_captured_and_stripped():
    raw = "Got it, that's a good point.\nNOTE_QUEUED: emoji reactions on tasks"
    r = _parse_reply(raw, cost=0.01)
    assert r.note_queued == "emoji reactions on tasks"
    assert "NOTE_QUEUED" not in r.display_text
    assert "Got it" in r.display_text


def test_revision_request_marker_captured_and_stripped():
    raw = "Sure thing.\nREVISION_REQUEST: add dark mode as a core feature in PRD"
    r = _parse_reply(raw, cost=0.02)
    assert r.revision_request == "add dark mode as a core feature in PRD"
    assert "REVISION_REQUEST" not in r.display_text


def test_multiple_markers_are_all_captured():
    # Unlikely in practice, but the parser should still strip all of them.
    raw = (
        "Done.\n"
        "NOTE_QUEUED: remember to add tag filters\n"
        "REVISION_REQUEST: no auth for v1"
    )
    r = _parse_reply(raw, cost=0.01)
    assert r.note_queued == "remember to add tag filters"
    assert r.revision_request == "no auth for v1"
    assert "NOTE_QUEUED" not in r.display_text
    assert "REVISION_REQUEST" not in r.display_text


def test_cost_passthrough():
    r = _parse_reply("hi", cost=0.12345)
    assert r.cost_usd == 0.12345
