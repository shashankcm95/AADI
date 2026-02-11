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
        assert ":vicinity" in result["ExpressionAttributeValues"]
        assert ":sent_at" in result["ExpressionAttributeValues"]

    def test_status_field_uses_alias(self):
        """'status' is a reserved word — should be aliased to #s."""
        plan = UpdatePlan(set_fields={"status": "SENT_TO_DESTINATION"})
        result = build_update_item_kwargs("s1", plan)

        assert "#s" in result["ExpressionAttributeNames"]
        assert result["ExpressionAttributeNames"]["#s"] == "status"
        assert "#s = :status" in result["UpdateExpression"]
        assert result["ExpressionAttributeValues"][":status"] == "SENT_TO_DESTINATION"

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
        assert "#s IN" in result["ConditionExpression"]
        assert ":c0" in result["ExpressionAttributeValues"]
        assert ":c1" in result["ExpressionAttributeValues"]
        assert result["ExpressionAttributeValues"][":c0"] == "PENDING_NOT_SENT"
        assert result["ExpressionAttributeValues"][":c1"] == "WAITING"

    def test_single_condition_status(self):
        plan = UpdatePlan(
            condition_allowed_statuses=("SENT_TO_DESTINATION",),
            set_fields={"receipt_mode": "HARD"},
        )
        result = build_update_item_kwargs("s1", plan)

        assert "#s IN (:c0)" in result["ConditionExpression"]

    def test_set_fields_and_condition_merge_values(self):
        """ExpressionAttributeValues should contain both SET values and condition values."""
        plan = UpdatePlan(
            condition_allowed_statuses=("PENDING_NOT_SENT",),
            set_fields={"status": "SENT_TO_DESTINATION", "sent_at": 1234},
        )
        result = build_update_item_kwargs("s1", plan)

        vals = result["ExpressionAttributeValues"]
        assert ":status" in vals  # from SET
        assert ":sent_at" in vals  # from SET
        assert ":c0" in vals  # from condition

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
