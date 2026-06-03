from __future__ import annotations

from pydantic import ValidationError

from visualizer.protocol import OperationRequest


def test_operation_request_validates_required_fields() -> None:
    request = OperationRequest.model_validate(
        {
            "structure": "singly_linked_list",
            "operation": "insert",
            "params": {"position": 2, "value": 9},
            "initial_state": {"data": [3, 5, 7]},
        }
    )
    assert request.params.position == 2


def test_supported_demo_operation_still_requires_params() -> None:
    try:
        OperationRequest.model_validate(
            {
                "structure": "sequential_list",
                "operation": "insert",
                "params": {"value": 9},
                "initial_state": {"data": [3, 5, 7]},
            }
        )
    except ValidationError as exc:
        assert "params.position" in str(exc)
    else:
        raise AssertionError("ValidationError expected")


def test_unsupported_course_operation_is_valid_request() -> None:
    request = OperationRequest.model_validate(
        {
            "structure": "sort",
            "operation": "quick_sort",
            "params": {"values": [5, 1, 3]},
            "initial_state": {"data": [5, 1, 3]},
        }
    )
    assert request.structure == "sort"
    assert request.operation == "quick_sort"


def test_initial_state_data_must_be_array() -> None:
    try:
        OperationRequest.model_validate(
            {
                "structure": "sequential_list",
                "operation": "search",
                "params": {"target": 3},
                "initial_state": {"data": "1,2,3"},
            }
        )
    except ValidationError as exc:
        assert "initial_state.data" in str(exc) or "data" in str(exc)
    else:
        raise AssertionError("ValidationError expected")
