from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INFRA_TEMPLATE = ROOT / "infrastructure" / "template.yaml"
ORDERS_TEMPLATE = ROOT / "services" / "orders" / "template.yaml"
RESTAURANTS_TEMPLATE = ROOT / "services" / "restaurants" / "template.yaml"
POS_TEMPLATE = ROOT / "services" / "pos-integration" / "template.yaml"
USERS_TEMPLATE = ROOT / "services" / "users" / "template.yaml"
CD_WORKFLOW = ROOT / ".github" / "workflows" / "cd.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_orders_template_allows_idempotency_header_and_exports_orders_table_name():
    text = _read(ORDERS_TEMPLATE)
    assert 'Idempotency-Key' in text
    assert 'OrdersTableName:' in text
    assert 'LocationGeofenceForceShadow' in text


def test_restaurants_template_exports_menus_table_name():
    text = _read(RESTAURANTS_TEMPLATE)
    assert 'MenusTableName:' in text


def test_pos_template_uses_explicit_cross_service_table_parameters():
    text = _read(POS_TEMPLATE)
    assert 'OrdersTableName:' in text
    assert 'MenusTableName:' in text
    assert 'HasOrdersTableName' in text
    assert 'HasMenusTableName' in text


def test_users_template_keeps_avatar_bucket_private_with_presigned_read_urls():
    text = _read(USERS_TEMPLATE)
    assert 'BlockPublicPolicy: true' in text
    assert 'RestrictPublicBuckets: true' in text
    assert 'PublicReadAvatars' not in text
    assert 'AVATAR_GET_URL_TTL_SECONDS' in text


def test_root_infra_exposes_cloudfront_distribution_outputs_and_pos_toggle():
    text = _read(INFRA_TEMPLATE)
    assert 'CustomerWebDistributionId:' in text
    assert 'AdminPortalDistributionId:' in text
    assert 'DeployPosIntegration:' in text
    assert 'PosIntegrationService:' in text
    assert 'LocationGeofenceCutoverEnabled:' in text
    assert 'LocationGeofenceForceShadow:' in text


def test_cd_workflow_uses_exported_distribution_output_keys():
    text = _read(CD_WORKFLOW)
    assert "OutputKey=='CustomerWebDistributionId'" in text
    assert "OutputKey=='AdminPortalDistributionId'" in text


def test_ci_workflow_runs_mobile_checks():
    ci_workflow = _read(ROOT / ".github" / "workflows" / "ci.yml")
    assert "mobile-check:" in ci_workflow
    assert "npm run test --workspace=packages/mobile-ios -- --runInBand" in ci_workflow


def test_cd_workflow_verifies_critical_api_routes_post_deploy():
    text = _read(CD_WORKFLOW)
    assert "Verify Deployed API Route Contracts" in text
    assert "./scripts/verify_http_api_routes.sh \"$ORDERS_API_URL\"" in text
    assert "POST /v1/orders/{order_id}/location" in text
    assert "./scripts/verify_http_api_routes.sh \"$USERS_API_URL\"" in text
    assert "POST /v1/users/me/avatar/upload-url" in text


def test_cd_workflow_runs_authenticated_post_deploy_smoke():
    text = _read(CD_WORKFLOW)
    assert "Acquire Smoke Test Token" in text
    assert "SMOKE_TEST_USERNAME" in text
    assert "SMOKE_TEST_PASSWORD" in text
    assert "aws cognito-idp initiate-auth" in text
    assert "Run Authenticated Post-Deploy Smoke" in text
    assert "./scripts/smoke_authenticated_order_flow.sh" in text


def test_root_infra_cloudfront_spa_routing_and_security_headers():
    text = _read(INFRA_TEMPLATE)
    # SPA routing: custom error responses for 403/404
    assert 'CustomErrorResponses:' in text
    assert 'ResponsePagePath: /index.html' in text
    # AWS managed SecurityHeadersPolicy
    assert '67f7725c-6f97-4210-82d7-5512b31e9d03' in text
    # PostConfirmation DLQ
    assert 'PostConfirmationDLQ' in text
    assert 'EventInvokeConfig' in text
    # LambdaConfig merge (reads before writing)
    assert 'describe_user_pool' in text
    # Admin auth flow removed
    assert 'ALLOW_ADMIN_USER_PASSWORD_AUTH' not in text
