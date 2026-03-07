#!/usr/bin/env python3
"""
Provision CloudWatch infrastructure-level dashboard.

Complements the order-flow observability script (services/orders/scripts/setup_cloudwatch_observability.py)
by covering infrastructure-level metrics:
  - Cognito auth metrics (sign-up, sign-in, token refresh)
  - CloudFront metrics (requests, errors, cache hit ratio)
  - PostConfirmation Lambda (invocations, errors, duration, DLQ depth)
  - Cross-service API Gateway aggregate (latency p50/p99, 4xx/5xx)
  - Cross-service DynamoDB aggregate (throttles, consumed capacity)

Usage:
  python infrastructure/scripts/setup_infra_dashboard.py \\
    --region us-east-1 \\
    --stack-name arrive-dev \\
    [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


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


def get_stack_outputs(region: str, stack_name: str) -> Dict[str, str]:
    """Get all outputs from the root CloudFormation stack."""
    result = run_aws([
        "cloudformation", "describe-stacks",
        "--region", region,
        "--stack-name", stack_name,
        "--query", "Stacks[0].Outputs",
        "--output", "json",
    ])
    if not result:
        return {}
    return {o["OutputKey"]: o["OutputValue"] for o in result}


def discover_function_name(region: str, stack_prefix: str, token: str) -> Optional[str]:
    """Find a Lambda function by name token and stack prefix."""
    functions = run_aws([
        "lambda", "list-functions",
        "--region", region,
        "--query", "Functions[].FunctionName",
        "--output", "json",
    ])
    candidates = [f for f in (functions or []) if stack_prefix in f and token in f]
    return candidates[0] if candidates else None


def discover_dynamodb_tables(region: str, stack_prefix: str) -> List[str]:
    """Find DynamoDB tables belonging to this stack."""
    result = run_aws([
        "dynamodb", "list-tables",
        "--region", region,
        "--output", "json",
    ])
    all_tables = result.get("TableNames", [])
    return [t for t in all_tables if stack_prefix in t]


def extract_api_id_from_url(url: str) -> Optional[str]:
    """Extract API Gateway ID from a URL like https://abc123.execute-api.us-east-1.amazonaws.com."""
    if not url:
        return None
    host = url.replace("https://", "").replace("http://", "").split("/")[0]
    api_id = host.split(".")[0]
    return api_id if api_id != host else None


def put_metric_filter(
    region: str,
    log_group_name: str,
    namespace: str,
    definition: MetricFilterDef,
    dry_run: bool = False,
) -> None:
    args = [
        "logs", "put-metric-filter",
        "--region", region,
        "--log-group-name", log_group_name,
        "--filter-name", definition.filter_name,
        "--filter-pattern", definition.pattern,
        "--metric-transformations",
        f"metricName={definition.metric_name},metricNamespace={namespace},metricValue=1",
    ]
    if dry_run:
        print(f"  [DRY RUN] aws {' '.join(args)}")
        return
    run_aws(args, expect_json=False)


def build_dashboard(
    region: str,
    namespace: str,
    user_pool_id: Optional[str],
    user_pool_client_id: Optional[str],
    distribution_ids: Dict[str, str],
    post_conf_function: Optional[str],
    dlq_name: Optional[str],
    post_conf_log_group: Optional[str],
    api_ids: Dict[str, str],
    dynamo_tables: List[str],
) -> Dict[str, Any]:
    widgets: List[Dict[str, Any]] = []

    # ── Row 0: Header ──
    widgets.append({
        "type": "text",
        "x": 0, "y": 0, "width": 24, "height": 2,
        "properties": {
            "markdown": (
                "# Infrastructure Observability\n"
                f"**Region:** `{region}` &nbsp; | &nbsp; "
                f"**Namespace:** `{namespace}` &nbsp; | &nbsp; "
                "**Auto-period:** widgets scale to selected time range"
            ),
        },
    })

    # ── Row 2: Cognito Sign-Up / Sign-In ──
    if user_pool_id:
        cognito_dims = ["UserPool", user_pool_id]
        if user_pool_client_id:
            cognito_dims += ["UserPoolClient", user_pool_client_id]

        widgets.append({
            "type": "metric",
            "x": 0, "y": 2, "width": 12, "height": 6,
            "properties": {
                "title": "Cognito: Sign-Up & Sign-In",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": [
                    ["AWS/Cognito", "SignUpSuccesses", *cognito_dims, {"label": "Sign-Up Successes"}],
                    [".", "SignInSuccesses", *cognito_dims, {"label": "Sign-In Successes"}],
                ],
            },
        })
        widgets.append({
            "type": "metric",
            "x": 12, "y": 2, "width": 12, "height": 6,
            "properties": {
                "title": "Cognito: Token Refresh & Federation",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": [
                    ["AWS/Cognito", "TokenRefreshSuccesses", *cognito_dims, {"label": "Token Refreshes"}],
                    [".", "FederationSuccesses", *cognito_dims, {"label": "Federation Successes"}],
                ],
            },
        })

    # ── Row 8: CloudFront Requests & Errors ──
    cf_request_metrics: List[List[Any]] = []
    cf_error_metrics: List[List[Any]] = []
    for label, dist_id in distribution_ids.items():
        if not dist_id:
            continue
        ns = "AWS/CloudFront" if not cf_request_metrics else "."
        cf_request_metrics.append(
            [ns, "Requests", "DistributionId", dist_id, "Region", "Global",
             {"label": f"{label.title()} Requests"}]
        )
        ns_e = "AWS/CloudFront" if not cf_error_metrics else "."
        cf_error_metrics.append(
            [ns_e, "4xxErrorRate", "DistributionId", dist_id, "Region", "Global",
             {"label": f"{label.title()} 4xx Rate"}]
        )
        cf_error_metrics.append(
            [".", "5xxErrorRate", "DistributionId", dist_id, "Region", "Global",
             {"label": f"{label.title()} 5xx Rate"}]
        )

    if cf_request_metrics:
        widgets.append({
            "type": "metric",
            "x": 0, "y": 8, "width": 12, "height": 6,
            "properties": {
                "title": "CloudFront: Requests",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": cf_request_metrics,
            },
        })
    if cf_error_metrics:
        widgets.append({
            "type": "metric",
            "x": 12, "y": 8, "width": 12, "height": 6,
            "properties": {
                "title": "CloudFront: Error Rates (4xx / 5xx)",
                "region": region,
                "stat": "Average",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Percent"}},
                "metrics": cf_error_metrics,
            },
        })

    # ── Row 14: CloudFront Cache Hit Rate (full width) ──
    cf_cache_metrics: List[List[Any]] = []
    for label, dist_id in distribution_ids.items():
        if not dist_id:
            continue
        ns = "AWS/CloudFront" if not cf_cache_metrics else "."
        cf_cache_metrics.append(
            [ns, "CacheHitRate", "DistributionId", dist_id, "Region", "Global",
             {"label": f"{label.title()} Cache Hit Rate"}]
        )
    if cf_cache_metrics:
        widgets.append({
            "type": "metric",
            "x": 0, "y": 14, "width": 24, "height": 6,
            "properties": {
                "title": "CloudFront: Cache Hit Rate",
                "region": region,
                "stat": "Average",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Percent", "min": 0, "max": 100}},
                "metrics": cf_cache_metrics,
            },
        })

    # ── Row 20: PostConfirmation Lambda ──
    if post_conf_function:
        widgets.append({
            "type": "metric",
            "x": 0, "y": 20, "width": 12, "height": 6,
            "properties": {
                "title": "PostConfirmation: Invocations & Errors",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": [
                    ["AWS/Lambda", "Invocations", "FunctionName", post_conf_function, {"label": "Invocations"}],
                    [".", "Errors", "FunctionName", post_conf_function, {"label": "Errors"}],
                    [".", "Throttles", "FunctionName", post_conf_function, {"label": "Throttles"}],
                ],
            },
        })
        widgets.append({
            "type": "metric",
            "x": 12, "y": 20, "width": 12, "height": 6,
            "properties": {
                "title": "PostConfirmation: Duration (p50 / p99)",
                "region": region,
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Milliseconds"}},
                "metrics": [
                    ["AWS/Lambda", "Duration", "FunctionName", post_conf_function,
                     {"label": "p50", "stat": "p50"}],
                    [".", "Duration", "FunctionName", post_conf_function,
                     {"label": "p99", "stat": "p99"}],
                ],
            },
        })

    # ── Row 26: DLQ Depth + PostConfirmation Error Logs ──
    if dlq_name:
        widgets.append({
            "type": "metric",
            "x": 0, "y": 26, "width": 12, "height": 6,
            "properties": {
                "title": "PostConfirmation DLQ Depth",
                "region": region,
                "stat": "Maximum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Messages"}},
                "metrics": [
                    ["AWS/SQS", "ApproximateNumberOfMessagesVisible",
                     "QueueName", dlq_name, {"label": "DLQ Depth"}],
                ],
            },
        })
    if post_conf_log_group:
        error_query = (
            f"SOURCE '{post_conf_log_group}' "
            "| fields @timestamp, message, error, user_id "
            "| filter level = \"ERROR\" "
            "| sort @timestamp desc "
            "| limit 100"
        )
        widgets.append({
            "type": "log",
            "x": 12, "y": 26, "width": 12, "height": 6,
            "properties": {
                "title": "PostConfirmation: Error Logs",
                "region": region,
                "query": error_query,
                "view": "table",
            },
        })

    # ── Row 32: API Gateway Aggregate ──
    api_latency_metrics: List[List[Any]] = []
    api_error_metrics: List[List[Any]] = []
    for label, api_id in api_ids.items():
        if not api_id:
            continue
        ns_l = "AWS/ApiGateway" if not api_latency_metrics else "."
        api_latency_metrics.append(
            [ns_l, "Latency", "ApiId", api_id, {"label": f"{label.title()} p50", "stat": "p50"}]
        )
        api_latency_metrics.append(
            [".", "Latency", "ApiId", api_id, {"label": f"{label.title()} p99", "stat": "p99"}]
        )
        ns_e = "AWS/ApiGateway" if not api_error_metrics else "."
        api_error_metrics.append(
            [ns_e, "4xx", "ApiId", api_id, {"label": f"{label.title()} 4xx"}]
        )
        api_error_metrics.append(
            [".", "5xx", "ApiId", api_id, {"label": f"{label.title()} 5xx"}]
        )

    if api_latency_metrics:
        widgets.append({
            "type": "metric",
            "x": 0, "y": 32, "width": 12, "height": 6,
            "properties": {
                "title": "API Gateway: Latency (p50 / p99)",
                "region": region,
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Milliseconds"}},
                "metrics": api_latency_metrics,
            },
        })
    if api_error_metrics:
        widgets.append({
            "type": "metric",
            "x": 12, "y": 32, "width": 12, "height": 6,
            "properties": {
                "title": "API Gateway: Error Counts (4xx / 5xx)",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": api_error_metrics,
            },
        })

    # ── Row 38: DynamoDB Aggregate ──
    if dynamo_tables:
        throttle_metrics: List[List[Any]] = []
        rcu_metrics: List[List[Any]] = []
        wcu_metrics: List[List[Any]] = []
        for idx, table_name in enumerate(dynamo_tables):
            ns = "AWS/DynamoDB" if idx == 0 else "."
            short_name = table_name.split("-")[-2] if "-" in table_name else table_name
            throttle_metrics.append(
                [ns, "ThrottledRequests", "TableName", table_name, {"label": f"{short_name} Throttles"}]
            )
            rcu_metrics.append(
                [ns, "ConsumedReadCapacityUnits", "TableName", table_name, {"label": f"{short_name} RCU"}]
            )
            wcu_metrics.append(
                [ns, "ConsumedWriteCapacityUnits", "TableName", table_name, {"label": f"{short_name} WCU"}]
            )

        widgets.append({
            "type": "metric",
            "x": 0, "y": 38, "width": 12, "height": 6,
            "properties": {
                "title": "DynamoDB: Throttled Requests",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Count"}},
                "metrics": throttle_metrics,
            },
        })
        widgets.append({
            "type": "metric",
            "x": 12, "y": 38, "width": 12, "height": 6,
            "properties": {
                "title": "DynamoDB: Consumed Capacity (RCU + WCU)",
                "region": region,
                "stat": "Sum",
                "period": 300,
                "view": "timeSeries",
                "stacked": False,
                "setPeriodToTimeRange": True,
                "yAxis": {"left": {"label": "Units"}},
                "metrics": [*rcu_metrics, *wcu_metrics],
            },
        })

    return {"widgets": widgets}


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up CloudWatch infrastructure dashboard.")
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
        help="AWS region (default: AWS_REGION/AWS_DEFAULT_REGION/us-east-1)",
    )
    parser.add_argument(
        "--stack-name",
        default="arrive-dev",
        help="CloudFormation stack name (default: arrive-dev)",
    )
    parser.add_argument(
        "--namespace",
        default="AADI/Infrastructure",
        help="CloudWatch metric namespace (default: AADI/Infrastructure)",
    )
    parser.add_argument(
        "--dashboard-name",
        default="",
        help="CloudWatch dashboard name (default: <stack-name>-Infrastructure-Dashboard)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only, do not mutate AWS resources.",
    )
    args = parser.parse_args()

    dashboard_name = args.dashboard_name or f"{args.stack_name}-Infrastructure-Dashboard"

    # ── Discovery ──
    print(f"Discovering resources for stack: {args.stack_name} in {args.region}...")

    try:
        outputs = get_stack_outputs(args.region, args.stack_name)
    except RuntimeError as exc:
        print(f"Error reading stack outputs: {exc}", file=sys.stderr)
        return 1

    user_pool_id = outputs.get("UserPoolId")
    user_pool_client_id = outputs.get("UserPoolClientId")
    print(f"  Cognito UserPool: {user_pool_id or 'NOT FOUND'}")

    distribution_ids = {
        "customer": outputs.get("CustomerWebDistributionId", ""),
        "admin": outputs.get("AdminPortalDistributionId", ""),
    }
    for label, did in distribution_ids.items():
        print(f"  CloudFront {label}: {did or 'NOT FOUND'}")

    post_conf_function = discover_function_name(args.region, args.stack_name, "PostConfirmation")
    post_conf_log_group = f"/aws/lambda/{post_conf_function}" if post_conf_function else None
    print(f"  PostConfirmation Lambda: {post_conf_function or 'NOT FOUND'}")

    dlq_name = f"{args.stack_name}-post-confirmation-dlq"
    dlq_url = outputs.get("PostConfirmationDLQUrl")
    if not dlq_url:
        dlq_name = None
    print(f"  PostConfirmation DLQ: {dlq_name or 'NOT FOUND'}")

    api_ids: Dict[str, str] = {}
    for key, label in [("OrdersApiUrl", "orders"), ("RestaurantsApiUrl", "restaurants"),
                        ("UsersApiUrl", "users"), ("PosIntegrationApiUrl", "pos")]:
        url = outputs.get(key, "")
        api_id = extract_api_id_from_url(url)
        if api_id:
            api_ids[label] = api_id
            print(f"  API Gateway {label}: {api_id}")

    dynamo_tables = discover_dynamodb_tables(args.region, args.stack_name)
    print(f"  DynamoDB tables: {len(dynamo_tables)} found")

    # ── Metric Filters (PostConfirmation) ──
    post_conf_filters = [
        MetricFilterDef("AADI-Infra-ProfileCreated", "ProfileCreated",
                        '{ $.message = "profile_created" }'),
        MetricFilterDef("AADI-Infra-ProfileAlreadyExists", "ProfileAlreadyExists",
                        '{ $.message = "profile_already_exists" }'),
        MetricFilterDef("AADI-Infra-ProfileCreationFailed", "ProfileCreationFailed",
                        '{ $.message = "profile_creation_failed" }'),
        MetricFilterDef("AADI-Infra-PostConfirmationErrors", "PostConfirmationErrors",
                        '{ $.level = "ERROR" }'),
    ]

    if post_conf_log_group:
        print(f"\nSetting up metric filters on {post_conf_log_group}...")
        for f in post_conf_filters:
            print(f"  {f.filter_name} -> {f.metric_name}")
            put_metric_filter(args.region, post_conf_log_group, args.namespace, f, dry_run=args.dry_run)

    # ── Dashboard ──
    print(f"\nBuilding dashboard: {dashboard_name}")
    body = build_dashboard(
        region=args.region,
        namespace=args.namespace,
        user_pool_id=user_pool_id,
        user_pool_client_id=user_pool_client_id,
        distribution_ids=distribution_ids,
        post_conf_function=post_conf_function,
        dlq_name=dlq_name,
        post_conf_log_group=post_conf_log_group,
        api_ids=api_ids,
        dynamo_tables=dynamo_tables,
    )

    dashboard_json = json.dumps(body)
    print(f"  Dashboard has {len(body['widgets'])} widgets")

    if args.dry_run:
        print(f"\n[DRY RUN] Would create dashboard: {dashboard_name}")
        print(json.dumps(body, indent=2))
        return 0

    run_aws([
        "cloudwatch", "put-dashboard",
        "--region", args.region,
        "--dashboard-name", dashboard_name,
        "--dashboard-body", dashboard_json,
    ])
    print(f"\nDashboard '{dashboard_name}' created/updated successfully.")
    print(f"View at: https://{args.region}.console.aws.amazon.com/cloudwatch/home"
          f"?region={args.region}#dashboards:name={dashboard_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
