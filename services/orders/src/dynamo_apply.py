from typing import Any, Dict, Optional, Tuple

from engine import UpdatePlan


def build_update_item_kwargs(order_id: str, plan: UpdatePlan) -> Optional[Dict[str, Any]]:
    """
    Convert UpdatePlan -> kwargs for DynamoDB Table.update_item.

    Returns None if the plan has no storage changes (only a response).
    """
    if not plan.set_fields and not plan.remove_fields:
        return None

    expr_names: Dict[str, str] = {}
    expr_values: Dict[str, Any] = {}
    parts = []

    # SET ...
    if plan.set_fields:
        set_chunks = []
        for k, v in plan.set_fields.items():
            # Always alias status because it's commonly reserved / used in conditions
            if k == "status":
                expr_names["#s"] = "status"
                set_chunks.append("#s = :status")
                expr_values[":status"] = v
            else:
                ph = f":{k}"
                set_chunks.append(f"{k} = {ph}")
                expr_values[ph] = v
        parts.append("SET " + ", ".join(set_chunks))

    # REMOVE ...
    if plan.remove_fields:
        parts.append("REMOVE " + ", ".join(plan.remove_fields))

    kwargs: Dict[str, Any] = {
        "Key": {"order_id": order_id},
        "UpdateExpression": " ".join(parts),
        "ExpressionAttributeValues": expr_values,
    }
    if expr_names:
        kwargs["ExpressionAttributeNames"] = expr_names

    # Condition: allowed statuses (idempotency / state-safety)
    if plan.condition_allowed_statuses:
        expr_names = kwargs.get("ExpressionAttributeNames", {})
        expr_names["#s"] = "status"
        kwargs["ExpressionAttributeNames"] = expr_names

        cond_vals = {}
        cond_list = []
        for i, s in enumerate(plan.condition_allowed_statuses):
            ph = f":c{i}"
            cond_vals[ph] = s
            cond_list.append(ph)

        kwargs["ConditionExpression"] = f"#s IN ({', '.join(cond_list)})"
        kwargs["ExpressionAttributeValues"] = {**kwargs["ExpressionAttributeValues"], **cond_vals}

    return kwargs

