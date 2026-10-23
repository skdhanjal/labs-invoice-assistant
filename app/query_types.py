"""Typed query and response models used by the invoice assistant."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Literal, Optional, Tuple, TypedDict, Union

NoAnswerReason = Literal[
    "missing_json",
    "invalid_json",
    "invalid_query_spec",
    "model_declined",
    "unsupported_query_field",
    "unsupported_grouping",
    "invalid_group_by",
    "unknown_column",
    "invalid_filters",
    "invalid_filter",
    "invalid_aggregate",
    "unsupported_aggregate",
    "invalid_sort",
    "invalid_limit",
    "unsupported_query_combination",
    "empty_aggregate",
    "invalid_filter_value",
    "no_customer_invoices",
]
FilterOperator = Literal["=", "!="]
AggregateFunction = Literal["count", "sum", "min", "max"]
SortDirection = Literal["asc", "desc"]
AggregateValue = Union[int, float, str]


class NoAnswerResponse(TypedDict):
    answer_kind: Literal["no_answer"]
    reason: NoAnswerReason


class QueryRowsResponse(TypedDict):
    results: List[dict[str, Any]]


class AggregateResponse(QueryRowsResponse):
    value: AggregateValue


@dataclass(frozen=True)
class NoAnswer:
    reason: NoAnswerReason

    def to_response(self) -> NoAnswerResponse:
        return {"answer_kind": "no_answer", "reason": self.reason}


@dataclass(frozen=True)
class QueryFilter:
    column: str
    operator: FilterOperator
    value: object


@dataclass(frozen=True)
class QueryAggregate:
    function: AggregateFunction
    column: Optional[str]


@dataclass(frozen=True)
class QuerySort:
    column: str
    direction: SortDirection


@dataclass(frozen=True)
class QuerySpec:
    filters: Tuple[QueryFilter, ...]
    aggregate: Optional[QueryAggregate]
    sort: Optional[QuerySort]
    limit: Optional[int]


QueryResponse = Union[NoAnswerResponse, QueryRowsResponse, AggregateResponse]
