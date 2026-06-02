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
