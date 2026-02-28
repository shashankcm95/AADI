#!/usr/bin/env python3
"""
Provision CloudWatch observability for order-flow testing.

What this script sets up:
1) CloudWatch Logs retention for the discovered service Lambda log groups.
2) CloudWatch metric filters for key order-flow milestones and errors.
3) A CloudWatch dashboard with service-level metrics and Logs Insights widgets.

Usage:
  python scripts/setup_cloudwatch_observability.py \
    --region us-east-1 \
    --stack-prefix arrive-fresh
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence


AWS_ALLOWED_RETENTION_DAYS = {
    1,
    3,
    5,
    7,
    14,
    30,
    60,
    90,
    120,
    150,
    180,
    365,
    400,
    545,
    731,
    1096,
    1827,
    2192,
    2557,
    2922,
    3288,
    3653,
}


@dataclass(frozen=True)
class MetricFilterDef:
    filter_name: str
    metric_name: str
    pattern: str


def run_aws(args: Sequence[str], expect_json: bool = True) -> Any:
    cmd = ["aws", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    if not expect_json:
        return proc.stdout.strip()
    output = proc.stdout.strip()
    if not output:
        return {}
    return json.loads(output)


def list_lambda_functions(region: str) -> List[Dict[str, str]]:
    return run_aws(
        [
            "lambda",
            "list-functions",
            "--region",
            region,
            "--query",
            "Functions[].{name:FunctionName,last_modified:LastModified}",
            "--output",
            "json",
        ]
    )


def select_latest_function_name(
    functions: Iterable[Dict[str, str]],
    required_tokens: Sequence[str],
    stack_prefix: Optional[str] = None,
) -> Optional[str]:
    candidates = []
    for fn in functions:
        name = str(fn.get("name") or "")
        if not name:
            continue
        if stack_prefix and stack_prefix not in name:
            continue
        if not all(token in name for token in required_tokens):
            continue
        candidates.append(fn)

    if not candidates and stack_prefix:
        # Fallback: if stack prefix mismatch, still try token-only match.
        for fn in functions:
            name = str(fn.get("name") or "")
            if name and all(token in name for token in required_tokens):
                candidates.append(fn)

    if not candidates:
        return None

    candidates.sort(key=lambda item: str(item.get("last_modified") or ""))
    return str(candidates[-1]["name"])


def ensure_log_group(region: str, log_group_name: str) -> None:
    try:
        run_aws(
            [
                "logs",
                "create-log-group",
                "--region",
                region,
                "--log-group-name",
                log_group_name,
            ],
            expect_json=False,
        )
    except RuntimeError as exc:
        text = str(exc)
        if "ResourceAlreadyExistsException" in text:
            return
        raise


def put_retention_policy(region: str, log_group_name: str, retention_days: int) -> None:
    run_aws(
        [
            "logs",
            "put-retention-policy",
            "--region",
            region,
            "--log-group-name",
            log_group_name,
            "--retention-in-days",
            str(retention_days),
        ],
        expect_json=False,
    )


def put_metric_filter(
    region: str,
    log_group_name: str,
    namespace: str,
    definition: MetricFilterDef,
) -> None:
    run_aws(
        [
            "logs",
            "put-metric-filter",
            "--region",
            region,
            "--log-group-name",
            log_group_name,
            "--filter-name",
            definition.filter_name,
            "--filter-pattern",
            definition.pattern,
            "--metric-transformations",
            (
                f"metricName={definition.metric_name},"
                f"metricNamespace={namespace},"
                "metricValue=1"
            ),
        ],
        expect_json=False,
    )


def build_dashboard(
    region: str,
    namespace: str,
    orders_log_group: str,
    geofence_log_group: Optional[str],
    service_log_groups: Dict[str, str],
    lambda_functions: Dict[str, str],
) -> Dict[str, Any]:
    # Key funnel metrics — the critical path that matters at a glance
    metrics_funnel = [
        [namespace, "OrdersCreated"],
        [".", "DispatchSent"],
        [".", "OrdersCompleted"],
        [".", "OrdersCancelled"],
    ]

    # Detailed operational metrics — for drill-down debugging
    metrics_events_detail = [
        [namespace, "LocationIngested"],
        [".", "VicinityUpdatesStarted"],
        [".", "VicinityUpdatesCompleted"],
        [".", "OrdersAcknowledged"],
        [".", "RestaurantStatusUpdated"],
        [".", "SameLocationBootstrapTriggered"],
    ]

    metrics_vicinity_health = [
        [namespace, "VicinityUpdatesStarted"],
        [".", "VicinityUpdatesCompleted"],
        [".", "VicinityUpdatesSuppressed"],
        [".", "OrderUpdateFailed"],
    ]

    metrics_business_kpis = [
        [namespace, "OrdersCreated"],
        [".", "OrdersCompleted"],
        [".", "OrdersCancelled"],
        [".", "OrdersAcknowledged"],
        [".", "OrdersFailed"],
    ]

    metrics_geofence = []
    if geofence_log_group:
        metrics_geofence = [
            [namespace, "GeofenceShadowRecorded"],
            [".", "GeofenceCutoverApplied"],
            [".", "GeofenceNoCandidateOrder"],
            [".", "GeofenceDuplicateSuppressed"],
        ]

    error_metric_names = ["OrdersErrors"]
    if "users" in service_log_groups:
        error_metric_names.append("UsersErrors")
    if "restaurants" in service_log_groups:
        error_metric_names.append("RestaurantsErrors")
    if "pos_integration" in service_log_groups:
        error_metric_names.append("PosIntegrationErrors")
    if geofence_log_group:
        error_metric_names.append("GeofenceErrors")
    error_metrics = []
    for idx, metric_name in enumerate(error_metric_names):
        if idx == 0:
            error_metrics.append([namespace, metric_name])
        else:
            error_metrics.append([".", metric_name])

    lambda_invocation_metrics: List[List[str]] = []
    lambda_error_metrics: List[List[str]] = []
    for service_name, function_name in lambda_functions.items():
        if not function_name:
            continue
        label_prefix = service_name.replace("_", " ").title()
        lambda_invocation_metrics.append(
            [
                "AWS/Lambda",
                "Invocations",
                "FunctionName",
                function_name,
                {"label": f"{label_prefix} Invocations"},
            ]
        )
        lambda_error_metrics.append(
            [
                ".",
                "Errors",
                "FunctionName",
                function_name,
                {"label": f"{label_prefix} Errors"},
            ]
        )

    lifecycle_groups = [orders_log_group]
    if geofence_log_group:
        lifecycle_groups.append(geofence_log_group)
    for service, group in service_log_groups.items():
        if service == "orders":
            continue
        lifecycle_groups.append(group)
    lifecycle_groups = list(dict.fromkeys(lifecycle_groups))

    # Per AWS Dashboard Body Structure docs, log widget queries MUST embed
    # log groups using SOURCE directives inside the query string itself.
    # A separate logGroupNames property does NOT work.
    source_prefix = " | ".join(f"SOURCE '{g}'" for g in lifecycle_groups)

    lifecycle_query = (
        f"{source_prefix} "
        "| fields @timestamp, service, handler, message, order_id, restaurant_id, customer_id, "
        "event, status, new_status, arrival_status, detail "
        "| filter message in ["
        "\"create_order_success\",\"location_ingested\",\"vicinity_update_started\","
        "\"capacity_decision\",\"state_transition_decided\",\"order_updated\",\"vicinity_update_completed\","
        "\"vicinity_update_suppressed\",\"cancel_order_completed\",\"ack_order_completed\","
        "\"same_location_bootstrap_triggered\",\"same_location_notice_attached\",\"shadow_event_recorded\","
        "\"cutover_event_applied\",\"status_update_completed\",\"order_update_failed\""
        "] "
        "| sort @timestamp desc "
        "| limit 250"
    )

    error_query = (
        f"{source_prefix} "
        "| fields @timestamp, service, handler, message, order_id, restaurant_id, error_type, detail, exception "
        "| filter level = \"ERROR\" "
        "| sort @timestamp desc "
        "| limit 250"
    )

    pending_query = (
        f"{source_prefix} "
        "| fields @timestamp, message, order_id, event, status, new_status, arrival_status, reason, detail "
        "| filter message in ["
        "\"vicinity_update_started\",\"vicinity_update_suppressed\",\"capacity_decision\","
        "\"state_transition_decided\",\"vicinity_update_completed\",\"cutover_event_applied\",\"shadow_event_recorded\""
        "] "
        "| filter status in [\"PENDING_NOT_SENT\",\"WAITING_FOR_CAPACITY\"] "
        "or new_status in [\"PENDING_NOT_SENT\",\"WAITING_FOR_CAPACITY\"] "
        "or arrival_status in [\"5_MIN_OUT\",\"PARKING\",\"AT_DOOR\"] "
        "| sort @timestamp desc "
        "| limit 250"
    )

    # Lambda p99 duration metrics
    lambda_duration_metrics: List[List[Any]] = []
    for idx, (service_name, function_name) in enumerate(lambda_functions.items()):
        if not function_name:
            continue
        label_prefix = service_name.replace("_", " ").title()
        ns = "AWS/Lambda" if idx == 0 else "."
        lambda_duration_metrics.append(
            [
                ns,
                "Duration",
                "FunctionName",
                function_name,
                {"label": f"{label_prefix} p99", "stat": "p99"},
            ]
        )

    # Order Status Distribution — Logs Insights query counting orders by current status
    status_distribution_query = (
        f"{source_prefix} "
        "| filter message in ["
        "\"create_order_success\",\"status_update_completed\",\"cancel_order_completed\","
        "\"vicinity_update_completed\",\"ack_order_completed\"" 
        "] "
        "| stats count(*) as cnt by message "
        "| sort cnt desc"
    )

    # ── Widget assembly ──────────────────────────────────────────────────

    widgets: List[Dict[str, Any]] = [
        # Row 0: Dashboard header
        {
            "type": "text",
            "x": 0,
            "y": 0,
            "width": 24,
            "height": 2,
            "properties": {
                "markdown": (
                    "# Order Flow Observability\n"
                    f"**Environment:** `{region}` &nbsp; | &nbsp; "
                    f"**Namespace:** `{namespace}` &nbsp; | &nbsp; "
                    "**Auto-period:** widgets scale to selected time range"
                ),
            },
        },
        # Row 2: Order Funnel + Business KPIs
        {
            "type": "metric",
            "x": 0,
            "y": 2,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Order Funnel (Created → Dispatched → Completed)",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": metrics_funnel,
            },
        },
        {
            "type": "metric",
            "x": 12,
            "y": 2,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Order Business KPIs",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": metrics_business_kpis,
            },
        },
        # Row 8: Detailed Event Breakdown + Service Errors
        {
            "type": "metric",
            "x": 0,
            "y": 8,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Detailed Event Breakdown",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": metrics_events_detail,
            },
        },
        {
            "type": "metric",
            "x": 12,
            "y": 8,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Service Errors",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": error_metrics,
            },
        },
    ]

    # Row 14: Lambda Performance + Lambda Invocations
    if lambda_duration_metrics:
        widgets.append(
            {
                "type": "metric",
                "x": 0,
                "y": 14,
                "width": 12,
                "height": 6,
                "properties": {
                    "title": "Lambda Performance (p99 Duration)",
                    "region": region,
                    "stat": "p99",
                    "period": 300,
                    "view": "timeSeries",
                    "stacked": False,
                    "setPeriodToTimeRange": True,
                    "yAxis": {"left": {"label": "Milliseconds"}},
                    "metrics": lambda_duration_metrics,
                },
            }
        )

    widgets.append(
        {
            "type": "metric",
            "x": 12 if lambda_duration_metrics else 0,
            "y": 14,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Lambda Invocations / Errors",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": [*lambda_invocation_metrics, *lambda_error_metrics],
            },
        }
    )

    # Row 20: Vicinity Health + Geofence
    widgets.append(
        {
            "type": "metric",
            "x": 0,
            "y": 20,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Vicinity Event Health",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": metrics_vicinity_health,
            },
        }
    )

    if metrics_geofence:
        widgets.append(
            {
                "type": "metric",
                "x": 12,
                "y": 20,
                "width": 12,
                "height": 6,
                "properties": {
                    "title": "Geofence Event Handling",
                    "region": region,
                    "stat": "Sum",
                    "period": 300,
                    "view": "timeSeries",
                    "stacked": False,
                    "setPeriodToTimeRange": True,
                    "yAxis": {"left": {"label": "Count"}},
                    "metrics": metrics_geofence,
                },
            }
        )

    # Row 26: Capacity Utilization
    metrics_capacity = [
        [namespace, "CapacityReserved"],
        [".", "CapacityRejected"],
        [".", "CapacityRaceRollback"],
    ]
    widgets.append(
        {
            "type": "metric",
            "x": 0,
            "y": 26,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Capacity Utilization (Reserved vs Rejected)",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": metrics_capacity,
            },
        }
    )

    # Row 26 right: API Gateway Health (if API exists)
    api_gateway_metrics: List[List[Any]] = []
    for service_name, function_name in lambda_functions.items():
        if not function_name:
            continue
        label = service_name.replace("_", " ").title()
        # API Gateway metrics use the API name, but we approximate with Lambda
        # For full API Gateway metrics, users should add ApiId parameter
    widgets.append(
        {
            "type": "metric",
            "x": 12,
            "y": 26,
            "width": 12,
            "height": 6,
            "properties": {
                "title": "Order Expiration & Failure Rates",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": [
                    [namespace, "OrdersExpired"],
                    [".", "OrdersFailed"],
                    [".", "OrderUpdateFailed"],
                ],
            },
        }
    )

    # Row 32: Order Event Counts bar chart
    widgets.append(
        {
            "type": "log",
            "x": 0,
            "y": 32,
            "width": 24,
            "height": 6,
            "properties": {
                "title": "Order Event Counts (Business KPIs)",
                "region": region,
                "query": status_distribution_query,
                "view": "bar",
            },
        }
    )

    # Row 38+: Logs Insights detail tables
    widgets.extend(
        [
            {
                "type": "log",
                "x": 0,
                "y": 38,
                "width": 24,
                "height": 7,
                "properties": {
                    "title": "Order Lifecycle Timeline (Logs Insights)",
                    "region": region,
                    "query": lifecycle_query,
                    "view": "table",
                },
            },
            {
                "type": "log",
                "x": 0,
                "y": 45,
                "width": 24,
                "height": 7,
                "properties": {
                    "title": "Errors (Logs Insights)",
                    "region": region,
                    "query": error_query,
                    "view": "table",
                },
            },
            {
                "type": "log",
                "x": 0,
                "y": 52,
                "width": 24,
                "height": 7,
                "properties": {
                    "title": "Pending / Arrival Diagnostics (Logs Insights)",
                    "region": region,
                    "query": pending_query,
                    "view": "table",
                },
            },
        ]
    )

    return {"widgets": widgets}


def validate_retention_days(value: int) -> int:
    if value not in AWS_ALLOWED_RETENTION_DAYS:
        valid = ", ".join(str(day) for day in sorted(AWS_ALLOWED_RETENTION_DAYS))
        raise ValueError(f"Invalid retention days {value}. Valid values: {valid}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up CloudWatch order-flow observability.")
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
        help="AWS region (default: AWS_REGION/AWS_DEFAULT_REGION/us-east-1)",
    )
    parser.add_argument(
        "--stack-prefix",
        default="arrive-fresh",
        help="Prefix used in deployed Lambda function names (default: arrive-fresh)",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="CloudWatch log retention days (AWS supported value, default: 30)",
    )
    parser.add_argument(
        "--namespace",
        default="AADI/OrderFlow",
        help="CloudWatch metric namespace for custom filters (default: AADI/OrderFlow)",
    )
    parser.add_argument(
        "--dashboard-name",
        default="",
        help="CloudWatch dashboard name (default: <stack-prefix>-OrderFlow-Observability)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only, do not mutate AWS resources.",
    )
    args = parser.parse_args()

    try:
        retention_days = validate_retention_days(args.retention_days)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    dashboard_name = args.dashboard_name or f"{args.stack_prefix}-OrderFlow-Observability"

    functions = list_lambda_functions(args.region)
    lambda_functions = {
        "orders": select_latest_function_name(functions, ("OrdersFunction",), args.stack_prefix),
        "geofence": select_latest_function_name(functions, ("GeofenceEventsFunction",), args.stack_prefix),
        "users": select_latest_function_name(functions, ("UsersFunction",), args.stack_prefix),
        "restaurants": select_latest_function_name(functions, ("RestaurantsFunction",), args.stack_prefix),
        "pos_integration": select_latest_function_name(functions, ("PosIntegrationFunction",), args.stack_prefix),
    }

    missing = [name for name, fn in lambda_functions.items() if not fn and name != "geofence"]
    if missing:
        print(
            "Warning: could not auto-discover Lambda functions for: "
            + ", ".join(missing)
            + ". Dashboard/log setup will continue for discovered services.",
            file=sys.stderr,
        )

    log_groups: Dict[str, str] = {}
    for service, fn_name in lambda_functions.items():
        if fn_name:
            log_groups[service] = f"/aws/lambda/{fn_name}"

    if "orders" not in log_groups:
        print("Error: Orders Lambda log group could not be discovered.", file=sys.stderr)
        return 1

    orders_log_group = log_groups["orders"]
    geofence_log_group = log_groups.get("geofence")

    orders_filters = [
        MetricFilterDef(
            filter_name="AADI-Orders-CreateOrderSuccess",
            metric_name="OrdersCreated",
            pattern='{ $.message = "create_order_success" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-LocationIngested",
            metric_name="LocationIngested",
            pattern='{ $.message = "location_ingested" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-VicinityUpdateStarted",
            metric_name="VicinityUpdatesStarted",
            pattern='{ $.message = "vicinity_update_started" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-VicinityUpdateCompleted",
            metric_name="VicinityUpdatesCompleted",
            pattern='{ $.message = "vicinity_update_completed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-DispatchSent",
            metric_name="DispatchSent",
            pattern='{ $.message = "vicinity_update_completed" && $.new_status = "SENT_TO_DESTINATION" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-SameLocationBootstrap",
            metric_name="SameLocationBootstrapTriggered",
            pattern='{ $.message = "same_location_bootstrap_triggered" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-SameLocationNotice",
            metric_name="SameLocationNoticeAttached",
            pattern='{ $.message = "same_location_notice_attached" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-Errors",
            metric_name="OrdersErrors",
            pattern='{ $.level = "ERROR" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-Cancelled",
            metric_name="OrdersCancelled",
            pattern='{ $.message = "cancel_order_completed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-Acknowledged",
            metric_name="OrdersAcknowledged",
            pattern='{ $.message = "ack_order_completed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-RestaurantStatusUpdated",
            metric_name="RestaurantStatusUpdated",
            pattern='{ $.message = "status_update_completed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-VicinitySuppressed",
            metric_name="VicinityUpdatesSuppressed",
            pattern='{ $.message = "vicinity_update_suppressed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-UpdateFailed",
            metric_name="OrderUpdateFailed",
            pattern='{ $.message = "order_update_failed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-Completed",
            metric_name="OrdersCompleted",
            pattern='{ $.message = "status_update_completed" && $.final_status = "COMPLETED" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-Failed",
            metric_name="OrdersFailed",
            pattern='{ $.message = "create_order_failed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-CapacityReserved",
            metric_name="CapacityReserved",
            pattern='{ $.message = "capacity_decision" && $.reserved = true }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-CapacityRejected",
            metric_name="CapacityRejected",
            pattern='{ $.message = "capacity_decision" && $.reserved = false }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-CapacityRaceRollback",
            metric_name="CapacityRaceRollback",
            pattern='{ $.message = "conditional_check_failed_race" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Orders-OrderExpired",
            metric_name="OrdersExpired",
            pattern='{ $.message = "expired" }',
        ),
    ]

    geofence_filters = [
        MetricFilterDef(
            filter_name="AADI-Geofence-ShadowRecorded",
            metric_name="GeofenceShadowRecorded",
            pattern='{ $.message = "shadow_event_recorded" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Geofence-CutoverApplied",
            metric_name="GeofenceCutoverApplied",
            pattern='{ $.message = "cutover_event_applied" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Geofence-NoCandidateOrder",
            metric_name="GeofenceNoCandidateOrder",
            pattern='{ $.message = "no_candidate_order" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Geofence-DuplicateSuppressed",
            metric_name="GeofenceDuplicateSuppressed",
            pattern='{ $.message = "duplicate_event_suppressed" }',
        ),
        MetricFilterDef(
            filter_name="AADI-Geofence-Errors",
            metric_name="GeofenceErrors",
            pattern='{ $.level = "ERROR" }',
        ),
    ]

    service_error_filters = {
        "users": MetricFilterDef(
            filter_name="AADI-Users-Errors",
            metric_name="UsersErrors",
            pattern='{ $.level = "ERROR" }',
        ),
        "restaurants": MetricFilterDef(
            filter_name="AADI-Restaurants-Errors",
            metric_name="RestaurantsErrors",
            pattern='{ $.level = "ERROR" }',
        ),
        "pos_integration": MetricFilterDef(
            filter_name="AADI-PosIntegration-Errors",
            metric_name="PosIntegrationErrors",
            pattern='{ $.level = "ERROR" }',
        ),
    }

    dashboard_body = build_dashboard(
        region=args.region,
        namespace=args.namespace,
        orders_log_group=orders_log_group,
        geofence_log_group=geofence_log_group,
        service_log_groups=log_groups,
        lambda_functions={k: v for k, v in lambda_functions.items() if v},
    )

    print("=== CloudWatch Observability Setup ===")
    print(f"Region: {args.region}")
    print(f"Stack prefix: {args.stack_prefix}")
    print(f"Dashboard: {dashboard_name}")
    print(f"Retention days: {retention_days}")
    print("Discovered log groups:")
    for service, group in sorted(log_groups.items()):
        print(f"  - {service}: {group}")
    if not geofence_log_group:
        print("  - geofence: not discovered (continuing without geofence-specific widgets/metrics)")

    if args.dry_run:
        print("\nDry run enabled. No AWS resources were changed.")
        print(json.dumps(dashboard_body, indent=2))
        return 0

    # Ensure log groups + retention
    for group in log_groups.values():
        ensure_log_group(args.region, group)
        put_retention_policy(args.region, group, retention_days)

    # Metric filters for orders flow
    for definition in orders_filters:
        put_metric_filter(args.region, orders_log_group, args.namespace, definition)

    # Metric filters for geofence consumer (if present)
    if geofence_log_group:
        for definition in geofence_filters:
            put_metric_filter(args.region, geofence_log_group, args.namespace, definition)

    # Error metric filters for other services
    for service, definition in service_error_filters.items():
        group = log_groups.get(service)
        if not group:
            continue
        put_metric_filter(args.region, group, args.namespace, definition)

    run_aws(
        [
            "cloudwatch",
            "put-dashboard",
            "--region",
            args.region,
            "--dashboard-name",
            dashboard_name,
            "--dashboard-body",
            json.dumps(dashboard_body),
        ],
        expect_json=False,
    )

    # ── CloudWatch Alarms ─────────────────────────────────────────────────
    alarm_definitions = [
        {
            "name": f"{args.stack_prefix}-ErrorRateSpike",
            "description": "Error rate exceeds threshold — potential incident",
            "metric": "OrdersErrors",
            "threshold": 5,
            "period": 300,
            "evaluation_periods": 1,
            "comparison": "GreaterThanThreshold",
        },
        {
            "name": f"{args.stack_prefix}-DispatchFailure",
            "description": "Order DynamoDB update failed — capacity leak risk",
            "metric": "OrderUpdateFailed",
            "threshold": 0,
            "period": 300,
            "evaluation_periods": 1,
            "comparison": "GreaterThanThreshold",
        },
        {
            "name": f"{args.stack_prefix}-CapacityRaceDetected",
            "description": "TOCTOU race condition detected — capacity rollback triggered",
            "metric": "CapacityRaceRollback",
            "threshold": 0,
            "period": 300,
            "evaluation_periods": 1,
            "comparison": "GreaterThanThreshold",
        },
        {
            "name": f"{args.stack_prefix}-HighCapacityRejection",
            "description": "Capacity rejections exceeding threshold — restaurant may be overwhelmed",
            "metric": "CapacityRejected",
            "threshold": 10,
            "period": 300,
            "evaluation_periods": 2,
            "comparison": "GreaterThanThreshold",
        },
        {
            "name": f"{args.stack_prefix}-OrderCreationFailure",
            "description": "Order creation failures detected",
            "metric": "OrdersFailed",
            "threshold": 0,
            "period": 300,
            "evaluation_periods": 1,
            "comparison": "GreaterThanThreshold",
        },
    ]

    # Lambda duration alarms
    for service_name, function_name in lambda_functions.items():
        if not function_name:
            continue
        label = service_name.replace("_", " ").title()
        alarm_definitions.append({
            "name": f"{args.stack_prefix}-{label.replace(' ', '')}-HighLatency",
            "description": f"{label} Lambda p99 duration exceeding 10s (timeout risk)",
            "metric": "Duration",
            "threshold": 10000,
            "period": 300,
            "evaluation_periods": 2,
            "comparison": "GreaterThanThreshold",
            "stat": "p99",
            "namespace": "AWS/Lambda",
            "dimensions": [{"Name": "FunctionName", "Value": function_name}],
        })

    for alarm_def in alarm_definitions:
        alarm_namespace = alarm_def.get("namespace", args.namespace)
        dimensions = alarm_def.get("dimensions", [])
        stat = alarm_def.get("stat", "Sum")

        cmd = [
            "cloudwatch",
            "put-metric-alarm",
            "--region", args.region,
            "--alarm-name", alarm_def["name"],
            "--alarm-description", alarm_def["description"],
            "--namespace", alarm_namespace,
            "--metric-name", alarm_def["metric"],
            "--statistic" if stat in ("Sum", "Average", "Maximum", "Minimum") else "--extended-statistic",
            stat,
            "--threshold", str(alarm_def["threshold"]),
            "--period", str(alarm_def["period"]),
            "--evaluation-periods", str(alarm_def["evaluation_periods"]),
            "--comparison-operator", alarm_def["comparison"],
            "--treat-missing-data", "notBreaching",
        ]
        if dimensions:
            dim_strs = [f"Name={d['Name']},Value={d['Value']}" for d in dimensions]
            cmd.extend(["--dimensions", *dim_strs])

        run_aws(cmd, expect_json=False)

    print(f"\nProvisioned {len(alarm_definitions)} CloudWatch alarms.")
    print("\nCloudWatch setup complete.")
    print(f"Dashboard URL template: https://{args.region}.console.aws.amazon.com/cloudwatch/home?region={args.region}#dashboards:name={dashboard_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
