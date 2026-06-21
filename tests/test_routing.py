"""Tests for cost routing: complexity tier -> model id."""

from __future__ import annotations

from claims_auditor.routing.cost_router import HAIKU, SONNET, Complexity, route


def test_simple_and_moderate_route_to_the_cheap_model() -> None:
    assert route(Complexity.SIMPLE) == HAIKU
    assert route(Complexity.MODERATE) == HAIKU


def test_hard_routes_to_the_strong_model() -> None:
    assert route(Complexity.HARD) == SONNET


def test_model_ids_are_the_current_claude_line() -> None:
    assert HAIKU == "claude-haiku-4-5"
    assert SONNET == "claude-sonnet-4-6"
