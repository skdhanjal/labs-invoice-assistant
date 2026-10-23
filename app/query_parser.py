"""Parsing and validation for untrusted model-generated invoice queries."""
from __future__ import annotations

import json
from typing import Any, Dict, Union

from query_types import (
    AggregateFunction,
    FilterOperator,
    NoAnswer,
    NoAnswerReason,
    QueryAggregate,
    QueryFilter,
    QuerySort,
    QuerySpec,
    SortDirection,
)


def no_answer(reason: NoAnswerReason) -> NoAnswer:
    return NoAnswer(reason)


def parse_model_response(raw: str) -> Union[Dict[str, Any], NoAnswer]:
    """Extract a query object from model text or return a safe no-answer."""
    start = raw.find("{")
    if start == -1:
        return no_answer("missing_json")

    try:
        spec, _ = json.JSONDecoder().raw_decode(raw, start)
    except json.JSONDecodeError:
        return no_answer("invalid_json")

    if not isinstance(spec, dict):
        return no_answer("invalid_query_spec")

    if spec.get("answer_kind") == "no_answer" or spec.get("no_answer") is True:
        return no_answer("model_declined")
    if "answer" in spec and spec["answer"] is None:
        return no_answer("model_declined")

    query_fields = {"filters", "aggregate", "sort", "limit", "group_by"}
    if not query_fields.intersection(spec):
        return no_answer("invalid_query_spec")

    return spec


def validate_query_spec(
    spec: Dict[str, Any], schema: Dict[str, Any]
) -> Union[QuerySpec, NoAnswer]:
    """Validate the model's query and convert it to a typed execution spec."""
    allowed_fields = {"filters", "aggregate", "sort", "limit"}
    if set(spec) - allowed_fields - {"group_by"}:
        return no_answer("unsupported_query_field")

    columns = {
        column["name"]: column["type"]
        for column in schema["columns"]
    }

    if "group_by" in spec:
        group_by = spec["group_by"]
        if not isinstance(group_by, str):
            return no_answer("invalid_group_by")
        if group_by not in columns:
            return no_answer("unknown_column")
        return no_answer("unsupported_grouping")

    filters = spec.get("filters", [])
    if not isinstance(filters, list):
        return no_answer("invalid_filters")
    query_filters = []
    for flt in filters:
        if not isinstance(flt, dict) or set(flt) - {"column", "op", "value"}:
            return no_answer("invalid_filter")
        column = flt.get("column")
        if not isinstance(column, str) or column not in columns:
            return no_answer("unknown_column")
        op = flt.get("op", "=")
        if "value" not in flt or not isinstance(op, str) or op not in {"=", "!="}:
            return no_answer("invalid_filter")
        operator: FilterOperator = "=" if op == "=" else "!="
        query_filters.append(
            QueryFilter(column=column, operator=operator, value=flt["value"])
        )

    aggregate = spec.get("aggregate")
    query_aggregate = None
    if aggregate is not None:
        if not isinstance(aggregate, dict) or set(aggregate) - {"fn", "column"}:
            return no_answer("invalid_aggregate")
        fn = aggregate.get("fn")
        if not isinstance(fn, str) or fn not in {"count", "sum", "min", "max"}:
            return no_answer("unsupported_aggregate")
        if fn == "count":
            column = aggregate.get("column")
            if column is not None and (not isinstance(column, str) or column not in columns):
                return no_answer("unknown_column")
            query_aggregate = QueryAggregate(function="count", column=column)
        else:
            column = aggregate.get("column")
            if not isinstance(column, str) or column not in columns:
                return no_answer("unknown_column")
            if fn == "sum" and columns[column] not in {"int", "float"}:
                return no_answer("invalid_aggregate")
            aggregate_function: AggregateFunction
            if fn == "sum":
                aggregate_function = "sum"
            elif fn == "min":
                aggregate_function = "min"
            else:
                aggregate_function = "max"
            query_aggregate = QueryAggregate(
                function=aggregate_function,
                column=column,
            )

    sort = spec.get("sort")
    query_sort = None
    if sort is not None:
        if not isinstance(sort, dict) or set(sort) - {"column", "dir"}:
            return no_answer("invalid_sort")
        column = sort.get("column")
        if not isinstance(column, str) or column not in columns:
            return no_answer("unknown_column")
        direction = sort.get("dir", "asc")
        if not isinstance(direction, str) or direction not in {"asc", "desc"}:
            return no_answer("invalid_sort")
        sort_direction: SortDirection = "asc" if direction == "asc" else "desc"
        query_sort = QuerySort(column=column, direction=sort_direction)

    limit = spec.get("limit")
    if limit is not None and (
        not isinstance(limit, int) or isinstance(limit, bool) or limit < 0
    ):
        return no_answer("invalid_limit")

    if aggregate is not None and (sort is not None or limit is not None):
        return no_answer("unsupported_query_combination")

    return QuerySpec(
        filters=tuple(query_filters),
        aggregate=query_aggregate,
        sort=query_sort,
        limit=limit,
    )
