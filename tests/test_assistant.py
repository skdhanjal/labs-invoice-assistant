"""Tests for the Invoice Query Assistant."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import main  # noqa: E402


def test_happy_path_overdue_sysco():
    out = main.ask(1049, "Show me my overdue Sysco invoices")
    assert [row["invoice_id"] for row in out["results"]] == ["INV-1001"]
    assert all(row["customer_id"] == 1049 for row in out["results"])


def test_malformed_json_degrades_to_no_answer():
    out = main.ask(1049, "How many invoices are open?")
    assert out["answer_kind"] == "no_answer"
    assert out["reason"] == "invalid_json"


def test_no_cross_tenant_leak():
    customers = {invoice["customer_id"] for invoice in main.INVOICES}
    questions = [
        "Show me my overdue Sysco invoices",
        "What is the total amount I owe?",
        "Who do I owe the most to?",
        "What is my biggest invoice?",
        "How many invoices are open?",
        "Is this a good deal?",
    ]

    for customer_id in customers:
        for question in questions:
            out = main.ask(customer_id, question)
            for row in out.get("results", []):
                assert row["customer_id"] == customer_id, (
                    f"Question {question!r} for customer {customer_id} "
                    f"returned invoice {row['invoice_id']} for customer "
                    f"{row['customer_id']}"
                )


def test_model_customer_filter_cannot_change_tenant(monkeypatch):
    monkeypatch.setattr(
        main.llm,
        "complete",
        lambda prompt: (
            '{"filters": [{"column": "customer_id", "op": "=", "value": 2210}], '
            '"sort": {"column": "amount", "dir": "desc"}, "limit": 1}'
        ),
    )

    out = main.ask(1049, "Show me my biggest invoice")

    assert [row["invoice_id"] for row in out["results"]] == ["INV-1003"]
    assert all(row["customer_id"] == 1049 for row in out["results"])


def test_unknown_column_returns_no_answer(monkeypatch):
    monkeypatch.setattr(
        main.llm,
        "complete",
        lambda prompt: (
            '{"filters": [{"column": "secret_margin", "op": "=", "value": 10}]}'
        ),
    )

    out = main.ask(1049, "Show me invoices by secret margin")

    assert out == {"answer_kind": "no_answer", "reason": "unknown_column"}


def test_empty_min_aggregate_returns_no_answer(monkeypatch):
    monkeypatch.setattr(
        main.llm,
        "complete",
        lambda prompt: (
            '{"aggregate": {"fn": "min", "column": "amount"}, '
            '"filters": [{"column": "vendor", "op": "=", "value": "Unknown"}]}'
        ),
    )

    out = main.ask(1049, "What is the smallest unknown vendor invoice?")

    assert out == {"answer_kind": "no_answer", "reason": "empty_aggregate"}


def test_messy_json_response_is_parsed(monkeypatch):
    monkeypatch.setattr(
        main.llm,
        "complete",
        lambda prompt: (
            'Here is the query:\n```json\n'
            '{"filters": [{"column": "vendor", "op": "=", "value": "Sysco"}]}'
            '\n```\nDone.'
        ),
    )

    out = main.ask(1049, "Show me Sysco invoices")

    assert {row["invoice_id"]
            for row in out["results"]} == {"INV-1001", "INV-1002"}
    assert all(row["customer_id"] == 1049 for row in out["results"])


@pytest.mark.parametrize(
    ("customer_id", "invoices"),
    [
        (9999, main.INVOICES),
        (1049, [row for row in main.INVOICES if row["customer_id"] != 1049]),
    ],
)
def test_customer_without_invoices_returns_before_model_call(
    customer_id, invoices, monkeypatch
):
    monkeypatch.setattr(main, "INVOICES", invoices)
    monkeypatch.setattr(
        main.llm,
        "complete",
        lambda prompt: pytest.fail(
            "model should not be called without invoices"),
    )

    out = main.ask(customer_id, "Show me my invoices")

    assert out == {
        "answer_kind": "no_answer",
        "reason": "no_customer_invoices",
    }


def test_prompt_contains_schema_and_question_but_no_invoice_rows():
    prompt = main.build_prompt("Show me my overdue Sysco invoices")

    assert "SCHEMA:" in prompt
    assert '"name": "vendor"' in prompt
    assert '"name": "customer_id"' in prompt
    assert "exactly one JSON object" in prompt
    assert "tenant scoping is applied by the service" in prompt
    assert '"answer_kind": "no_answer"' in prompt
    assert "QUESTION: Show me my overdue Sysco invoices" in prompt
    assert "INV-1001" not in prompt
    assert "INV-2001" not in prompt
    assert "REQUESTING CUSTOMER ID" not in prompt
