"""
Tests for dynamo_apply.build_update_item_kwargs.
Verifies the DynamoDB expression builder produces correct
UpdateExpression, ExpressionAttributeNames, and ConditionExpression.
"""
import pytest

from engine import UpdatePlan
from dynamo_apply import build_update_item_kwargs


class TestBuildUpdateItemKwargs:
    def test_returns_none_for_no_op_plan(self):
        """A plan with no set_fields or remove_fields should return None."""
        plan = UpdatePlan(response={"session_id": "s1", "status": "PENDING"})
        assert build_update_item_kwargs("s1", plan) is None

    def test_set_fields_basic(self):
        plan = UpdatePlan(set_fields={"vicinity": True, "sent_at": 1000})
        result = build_update_item_kwargs("s1", plan)

        assert result is not None
        assert result["Key"] == {"order_id": "s1"}
        assert "SET" in result["UpdateExpression"]
        
        # Verify values are present in EAV, regardless of placeholder name
        values = list(result["ExpressionAttributeValues"].values())
        assert True in values
        assert 1000 in values

    def test_status_field_uses_alias(self):
        """'status' should be aliased to avoid reserved word issues."""
        plan = UpdatePlan(set_fields={"status": "SENT_TO_DESTINATION"})
        result = build_update_item_kwargs("s1", plan)

        # Verify alias usage
        assert "ExpressionAttributeNames" in result
        names = result["ExpressionAttributeNames"]
        assert "status" in names.values()
        
        # Verify value matches
        values = list(result["ExpressionAttributeValues"].values())
        assert "SENT_TO_DESTINATION" in values

    def test_remove_fields(self):
        plan = UpdatePlan(
            set_fields={"status": "SENT_TO_DESTINATION"},
            remove_fields=("waiting_since", "suggested_start_at"),
        )
        result = build_update_item_kwargs("s1", plan)

        assert "REMOVE waiting_since, suggested_start_at" in result["UpdateExpression"]

    def test_remove_fields_only(self):
        plan = UpdatePlan(remove_fields=("old_field",))
        result = build_update_item_kwargs("s1", plan)

        assert result is not None
        assert "REMOVE old_field" in result["UpdateExpression"]
        assert "SET" not in result["UpdateExpression"]

    def test_condition_allowed_statuses(self):
        plan = UpdatePlan(
            condition_allowed_statuses=("PENDING_NOT_SENT", "WAITING"),
            set_fields={"status": "SENT_TO_DESTINATION"},
        )
        result = build_update_item_kwargs("s1", plan)

        assert "ConditionExpression" in result
        # Verify status is aliased in condition
        assert "status" in result["ExpressionAttributeNames"].values()
        
        # Verify condition values are present
        values = list(result["ExpressionAttributeValues"].values())
        assert "PENDING_NOT_SENT" in values
        assert "WAITING" in values

    def test_single_condition_status(self):
        plan = UpdatePlan(
            condition_allowed_statuses=("SENT_TO_DESTINATION",),
            set_fields={"receipt_mode": "HARD"},
        )
        result = build_update_item_kwargs("s1", plan)

        # Verify just one value in condition
        vals = result["ExpressionAttributeValues"]
        assert "SENT_TO_DESTINATION" in vals.values()

    def test_set_fields_and_condition_merge_values(self):
        """ExpressionAttributeValues should contain both SET values and condition values."""
        plan = UpdatePlan(
            condition_allowed_statuses=("PENDING_NOT_SENT",),
            set_fields={"status": "SENT_TO_DESTINATION", "sent_at": 1234},
        )
        result = build_update_item_kwargs("s1", plan)

        vals = list(result["ExpressionAttributeValues"].values())
        assert "SENT_TO_DESTINATION" in vals  # from SET
        assert 1234 in vals  # from SET
        assert "PENDING_NOT_SENT" in vals  # from condition

    def test_complex_plan(self):
        """Full plan with set, remove, and conditions."""
        plan = UpdatePlan(
            condition_allowed_statuses=("PENDING_NOT_SENT", "WAITING"),
            set_fields={
                "status": "SENT_TO_DESTINATION",
                "vicinity": True,
                "sent_at": 1000,
            },
            remove_fields=("waiting_since", "suggested_start_at"),
        )
        result = build_update_item_kwargs("order-123", plan)

        assert result["Key"] == {"order_id": "order-123"}
        assert "SET" in result["UpdateExpression"]
        assert "REMOVE" in result["UpdateExpression"]
        assert "ConditionExpression" in result
        assert len(result["ExpressionAttributeValues"]) == 5  # status, vicinity, sent_at, c0, c1
