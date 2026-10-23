"""Invoice Query Assistant service."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fake_llm import FakeLLM
from query_parser import (
    no_answer as _no_answer,
    parse_model_response,
    validate_query_spec,
)
from query_types import NoAnswer, QueryResponse, QuerySpec

llm = FakeLLM()

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "invoices.json")
with open(_DATA_PATH) as f:
    _DB = json.load(f)
INVOICES: List[Dict[str, Any]] = _DB["invoices"]
SCHEMA = _DB["schema"]


def _invoices_for_customer(customer_id: int) -> List[Dict[str, Any]]:
    return [invoice for invoice in INVOICES if invoice["customer_id"] == customer_id]


def build_prompt(question: str) -> str:
    return (
        "You convert invoice questions into query specs. You do not answer "
        "from invoice records.\n"
        f"SCHEMA: {json.dumps(SCHEMA)}\n"
        "Return exactly one JSON object with no Markdown or surrounding prose. "
        "Use only the exact column names in the schema. Supported query fields "
        "are filters, aggregate, sort, and limit. Filters are a list of "
        "objects with column, op, and value; op must be '=' or '!='. Do not "
        "include customer_id filters because tenant scoping is applied by the "
        "service. Aggregate must be an object with fn set to count, sum, min, "
        "or max; sum, min, and max require a schema column. Sort must be an "
        "object with column and optional dir set to asc or desc. Limit must "
        "be a non-negative integer. Grouping and all other query fields are "
        "unsupported. If the question cannot be expressed with these "
        "operations, return exactly {\"answer_kind\": \"no_answer\"}.\n"
        f"QUESTION: {question}\n"
    )


def run_query(spec: QuerySpec, customer_id: int) -> QueryResponse:
    """Run a validated query only against invoices owned by the requester."""
    rows = _invoices_for_customer(customer_id)
    
    for query_filter in spec.filters:
        if query_filter.column == "customer_id":
            continue
        if query_filter.operator == "=":
            rows = [row for row in rows if row.get(query_filter.column) == query_filter.value]
        elif query_filter.operator == "!=":
            rows = [row for row in rows if row.get(query_filter.column) != query_filter.value]

    aggregate = spec.aggregate
    if aggregate is not None:
        if aggregate.function == "count":
            return {"results": rows, "value": len(rows)}
        if aggregate.column is None:
            return _no_answer("invalid_aggregate").to_response()
        values = [row[aggregate.column] for row in rows]
        if aggregate.function == "sum":
            return {"results": rows, "value": sum(values)}
        if not values:
            return _no_answer("empty_aggregate").to_response()
        if aggregate.function == "min":
            return {"results": rows, "value": min(values)}
        return {"results": rows, "value": max(values)}

    query_sort = spec.sort
    if query_sort is not None:
        rows = sorted(
            rows,
            key=lambda row: row[query_sort.column],
            reverse=query_sort.direction == "desc",
        )
    if spec.limit is not None:
        rows = rows[: spec.limit]
    return {"results": rows}


def ask(customer_id: int, question: str) -> QueryResponse:
    if not _invoices_for_customer(customer_id):
        return _no_answer("no_customer_invoices").to_response()
    
    prompt = build_prompt(question)
    raw = llm.complete(prompt)
    spec = parse_model_response(raw)
    
    if isinstance(spec, NoAnswer):
        return spec.to_response()
    
    validated_spec = validate_query_spec(spec, SCHEMA)
    
    if isinstance(validated_spec, NoAnswer):
        return validated_spec.to_response()
    
    return run_query(validated_spec, customer_id)
