from typing import Any, Dict, Optional, List

from engine import UpdatePlan


class DynamoUpdateBuilder:
    """
    Helper to construct DynamoDB UpdateItem parameters safely.
    Manages expression attribute names/values to avoid collisions.
    """

    def __init__(self):
        self.set_clauses: List[str] = []
        self.remove_clauses: List[str] = []
        self.condition_clauses: List[str] = []
        self.names: Dict[str, str] = {}
        self.values: Dict[str, Any] = {}
        self._name_counter = 0
        self._val_counter = 0

    def add_set(self, field: str, value: Any) -> None:
        """Add a SET field = :value clause."""
        name_ref = self._get_name_ref(field)
        val_ref = self._get_val_ref(field)
        self.set_clauses.append(f"{name_ref} = {val_ref}")
        self.values[val_ref] = value

    def add_remove(self, field: str) -> None:
        """Add a REMOVE field clause."""
        # Simple field names only for now (no nested paths)
        self.remove_clauses.append(field)

    def add_condition_in(self, field: str, allowed_values: tuple) -> None:
        """Add a condition: field IN (:v1, :v2, ...)."""
        if not allowed_values:
            return

        name_ref = self._get_name_ref(field)
        val_refs = []
        for i, val in enumerate(allowed_values):
            # Use a distinctive prefix for condition values to avoid collision
            # though _get_val_ref unique counter handles it anyway
            ref = self._get_val_ref(f"cond_{i}")
            val_refs.append(ref)
            self.values[ref] = val

        self.condition_clauses.append(f"{name_ref} IN ({', '.join(val_refs)})")

    def build(self, key: Dict[str, Any]) -> Dict[str, Any]:
        """Generate the Boto3 update_item kwargs."""
        kwargs: Dict[str, Any] = {"Key": key}
        update_parts = []

        if self.set_clauses:
            update_parts.append("SET " + ", ".join(self.set_clauses))

        if self.remove_clauses:
            update_parts.append("REMOVE " + ", ".join(self.remove_clauses))

        if update_parts:
            kwargs["UpdateExpression"] = " ".join(update_parts)

        if self.condition_clauses:
            kwargs["ConditionExpression"] = " AND ".join(self.condition_clauses)

        if self.names:
            kwargs["ExpressionAttributeNames"] = self.names

        if self.values:
            kwargs["ExpressionAttributeValues"] = self.values

        return kwargs

    def _get_name_ref(self, field_name: str) -> str:
        """
        Get a safe attribute name reference (e.g., #n0).
        Always aliases to avoid reserved word issues.
        """
        # We could optimize to reuse refs, but simple unique generation is safer
        ref = f"#n{self._name_counter}"
        self._name_counter += 1
        self.names[ref] = field_name
        return ref

    def _get_val_ref(self, hint: str) -> str:
        """Get a unique value reference (e.g., :v0)."""
        ref = f":v{self._val_counter}"
        self._val_counter += 1
        return ref


def build_update_item_kwargs(order_id: str, plan: UpdatePlan) -> Optional[Dict[str, Any]]:
    """
    Convert UpdatePlan -> kwargs for DynamoDB Table.update_item.

    Returns None if the plan has no storage changes (only a response).
    """
    if not plan.set_fields and not plan.remove_fields:
        return None

    builder = DynamoUpdateBuilder()

    # SET ...
    if plan.set_fields:
        for k, v in plan.set_fields.items():
            builder.add_set(k, v)

    # REMOVE ...
    if plan.remove_fields:
        for field in plan.remove_fields:
            builder.add_remove(field)

    # Condition: allowed statuses (idempotency / state-safety)
    if plan.condition_allowed_statuses:
        builder.add_condition_in("status", plan.condition_allowed_statuses)

    return builder.build(key={"order_id": order_id})
