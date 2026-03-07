import pytest
import json
from unittest.mock import MagicMock, call

# conftest.py adds src/ to path
import utils

def test_decimal_default():
    """Test JSON serialization helper for Decimals."""
    from decimal import Decimal
    assert utils.decimal_default(Decimal('10.5')) == 10.5
    with pytest.raises(TypeError):
        utils.decimal_default("not-decimal")

def test_get_user_claims_valid():
    event = {
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'custom:role': 'restaurant_admin',
                        'custom:restaurant_id': 'r1',
                        'sub': 'user-123',
                        'cognito:username': 'admin-user'
                    }
                }
            }
        }
    }
    claims = utils.get_user_claims(event)
    assert claims['role'] == 'restaurant_admin'
    assert claims['restaurant_id'] == 'r1'
    assert claims['customer_id'] == 'user-123'
    assert claims['username'] == 'admin-user'

def test_get_user_claims_roleless_defaults_customer():
    event = {
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123',
                        'cognito:username': 'social-user'
                    }
                }
            }
        }
    }
    claims = utils.get_user_claims(event)
    assert claims['role'] == 'customer'
    assert claims['customer_id'] == 'user-123'

def test_get_user_claims_invalid():
    assert utils.get_user_claims({}) == {}

def test_is_admin_or_owner():
    # Admin
    assert utils._is_admin_or_owner({'role': 'admin'}, 'r1') is True
    # Owner
    assert utils._is_admin_or_owner({'role': 'restaurant_admin', 'restaurant_id': 'r1'}, 'r1') is True
    # Wrong Owner
    assert utils._is_admin_or_owner({'role': 'restaurant_admin', 'restaurant_id': 'r2'}, 'r1') is False
    # Customer
    assert utils._is_admin_or_owner({'role': 'customer'}, 'r1') is False

def test_require_customer_success():
    event = {
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'c1',
                        'custom:role': 'customer'
                    }
                }
            }
        }
    }
    customer_id, error = utils._require_customer(event)
    assert customer_id == 'c1'
    assert error is None

def test_require_customer_roleless_success():
    event = {
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'c1'
                    }
                }
            }
        }
    }
    customer_id, error = utils._require_customer(event)
    assert customer_id == 'c1'
    assert error is None

def test_require_customer_failures():
    # Missing claims
    cid, err = utils._require_customer({})
    assert cid is None
    assert err['statusCode'] == 401

    # Wrong role
    event_admin = {
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'a1',
                        'custom:role': 'admin'
                    }
                }
            }
        }
    }
    cid, err = utils._require_customer(event_admin)
    assert cid is None
    assert err['statusCode'] == 403

def test_geocode_success(monkeypatch):
    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value.read.return_value = json.dumps([
        {'lat': '30.2672', 'lon': '-97.7431'}
    ]).encode()
    
    monkeypatch.setattr(utils.urllib.request, 'urlopen', lambda req, **kwargs: mock_urlopen)
    
    result = utils.geocode_address("123 Main", "Austin", "TX", "78701")
    from decimal import Decimal
    assert result['lat'] == Decimal('30.2672')
    assert result['lon'] == Decimal('-97.7431')

def test_geocode_retry_unit_removal(monkeypatch):
    # First call fails (empty list), second succeeds
    responses = [
        json.dumps([]).encode(),  # 123 Main #101
        json.dumps([{'lat': '30.2672', 'lon': '-97.7431'}]).encode()  # 123 Main
    ]
    
    mock_urlopen = MagicMock()
    # side_effect needs to handle context manager usage
    # Simpler: Create two separate context managers or use a class
    
    class MockResponse:
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return self.data

    # We need to return a new response for each call
    iter_responses = iter(responses)
    def mock_open(req, **kwargs):
        return MockResponse(next(iter_responses))

    monkeypatch.setattr(utils.urllib.request, 'urlopen', mock_open)

    # Input with unit number
    result = utils.geocode_address("123 Main St #101", "Austin", "TX", "78701")
    from decimal import Decimal
    assert result['lat'] == Decimal('30.2672')

def test_extract_s3_object_key():
    assert utils._extract_s3_object_key("s3://bucket/key") == "key"
    assert utils._extract_s3_object_key("restaurants/123/img.jpg") == "restaurants/123/img.jpg"
    assert utils._extract_s3_object_key("https://bucket.s3.amazonaws.com/key.jpg") == "key.jpg"
    assert utils._extract_s3_object_key("") == ""
    assert utils._extract_s3_object_key(None) == ""

def test_normalize_restaurant_image_keys():
    # Success
    keys = ["s3://bucket/restaurants/r1/1.jpg", "restaurants/r1/2.jpg"]
    norm = utils._normalize_restaurant_image_keys(keys, "r1")
    assert norm == ["restaurants/r1/1.jpg", "restaurants/r1/2.jpg"]

    # Not List
    with pytest.raises(ValueError, match="must be a list"):
        utils._normalize_restaurant_image_keys("not-list", "r1")

    # Wrong Restaurant Prefix
    with pytest.raises(ValueError, match="must belong to this restaurant"):
        utils._normalize_restaurant_image_keys(["restaurants/OTHER/1.jpg"], "r1")

    # Too many
    many = [f"restaurants/r1/{i}.jpg" for i in range(6)]
    with pytest.raises(ValueError, match="maximum of 5"):
        utils._normalize_restaurant_image_keys(many, "r1")

def test_build_image_url(monkeypatch):
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://presigned.url"
    monkeypatch.setattr(utils, 's3_client', mock_s3)
    
    # Must patch access to env var if it was None at import time (but utils imports os.environ at top level)
    # The module level RESTAURANT_IMAGES_BUCKET is read at import time.
    # We need to patch the module attribute.
    monkeypatch.setattr(utils, 'RESTAURANT_IMAGES_BUCKET', 'test-bucket')

    url = utils._build_image_url("key.jpg")
    assert url == "https://presigned.url"
    mock_s3.generate_presigned_url.assert_called_with(
        'get_object',
        Params={'Bucket': 'test-bucket', 'Key': 'key.jpg'},
        ExpiresIn=3600
    )

def test_decorate_restaurant_response(monkeypatch):
    # Mock _build_image_url to avoid S3 calls
    monkeypatch.setattr(utils, '_build_image_url', lambda k: f"http://{k}")
    
    item = {
        "name": "Test Place",
        "restaurant_image_keys": ["restaurants/r1/1.jpg", "restaurants/r1/2.jpg"]
    }
    
    decorated = utils._decorate_restaurant_response(item)
    assert decorated['restaurant_images'] == ["http://restaurants/r1/1.jpg", "http://restaurants/r1/2.jpg"]
    assert decorated['image_url'] == "http://restaurants/r1/1.jpg"
    assert decorated['banner_image_url'] == "http://restaurants/r1/2.jpg"


def test_decorate_restaurant_response_adds_top_level_coordinates(monkeypatch):
    from decimal import Decimal
    monkeypatch.setattr(utils, '_build_image_url', lambda k: f"http://{k}")

    item = {
        "name": "Geo Place",
        "location": {"lat": Decimal('30.2672'), "lon": Decimal('-97.7431')},
        "restaurant_image_keys": [],
    }

    decorated = utils._decorate_restaurant_response(item)
    assert decorated['latitude'] == pytest.approx(30.2672)
    assert decorated['longitude'] == pytest.approx(-97.7431)


def test_dispatch_trigger_zone_normalization():
    assert utils.normalize_dispatch_trigger_zone("zone_2") == "ZONE_2"
    assert utils.normalize_dispatch_trigger_zone("parking") == "ZONE_2"
    assert utils.normalize_dispatch_trigger_event("ZONE_3") == "AT_DOOR"
    assert utils.normalize_dispatch_trigger_event("AT_DOOR") == "AT_DOOR"
    assert utils.normalize_dispatch_trigger_zone("unknown") is None


def test_get_geofence_radii_uses_global_zone_distances(monkeypatch):
    class MockConfigTable:
        @staticmethod
        def get_item(Key):
            assert Key["restaurant_id"] == "__GLOBAL__"
            return {"Item": {"zone_distances_m": {"ZONE_1": 2000, "ZONE_2": 250, "ZONE_3": 50}}}

    monkeypatch.setattr(utils, "config_table", MockConfigTable())
    radii = utils.get_geofence_radii_meters()
    assert radii == {"5_MIN_OUT": 2000, "PARKING": 250, "AT_DOOR": 50}


def test_get_global_zone_labels_uses_config(monkeypatch):
    class MockConfigTable:
        @staticmethod
        def get_item(Key):
            assert Key["restaurant_id"] == "__GLOBAL__"
            return {"Item": {"zone_labels": {"ZONE_1": "Far", "ZONE_2": "Queue", "ZONE_3": "Door"}}}

    monkeypatch.setattr(utils, "config_table", MockConfigTable())
    labels = utils.get_global_zone_labels()
    assert labels == {"ZONE_1": "Far", "ZONE_2": "Queue", "ZONE_3": "Door"}


# =============================================================================
# Geofence Geometry Tests
# =============================================================================

class TestBuildCirclePolygon:
    def test_polygon_is_closed(self):
        """First point must equal last point (closed ring)."""
        points = utils._build_circle_polygon(30.2672, -97.7431, 1000)
        assert len(points) > 2
        assert points[0] == points[-1]

    def test_correct_number_of_vertices(self):
        """Default 12 segments → 12+1 points (closed)."""
        points = utils._build_circle_polygon(30.2672, -97.7431, 1000, segments=12)
        assert len(points) == 13  # 12 + closing point

    def test_minimum_segments_enforced(self):
        """Segments < 8 are clamped to 8."""
        points = utils._build_circle_polygon(30.2672, -97.7431, 1000, segments=3)
        assert len(points) == 9  # max(8, 3) = 8 + closing point

    def test_coordinates_within_valid_range(self):
        """All coordinates must be in valid lon [-180, 180], lat [-90, 90]."""
        points = utils._build_circle_polygon(30.2672, -97.7431, 5000, segments=16)
        for lon, lat in points:
            assert -180 <= lon <= 180, f"Longitude {lon} out of range"
            assert -90 <= lat <= 90, f"Latitude {lat} out of range"

    def test_small_radius(self):
        """Small radius should still produce a valid polygon."""
        points = utils._build_circle_polygon(0.0, 0.0, 10)
        assert len(points) > 2
        assert points[0] == points[-1]


class TestUpsertRestaurantGeofences:
    def test_missing_lat_lon_returns_false(self, monkeypatch):
        """Missing lat or lon in location → returns False."""
        monkeypatch.setattr(utils, 'LOCATION_GEOFENCE_COLLECTION_NAME', 'test-collection')
        assert utils.upsert_restaurant_geofences('r1', {'lat': 30.0}) is False
        assert utils.upsert_restaurant_geofences('r1', {}) is False
        assert utils.upsert_restaurant_geofences('r1', None) is False

    def test_no_collection_returns_false(self, monkeypatch):
        """No geofence collection configured → returns False."""
        monkeypatch.setattr(utils, 'LOCATION_GEOFENCE_COLLECTION_NAME', '')
        assert utils.upsert_restaurant_geofences('r1', {'lat': 30.0, 'lon': -97.0}) is False

    def test_creates_three_geofence_zones(self, monkeypatch):
        """Valid location → 3 geofence entries (one per zone)."""
        mock_client = MagicMock()
        mock_client.batch_put_geofence.return_value = {'Errors': []}
        monkeypatch.setattr(utils, 'LOCATION_GEOFENCE_COLLECTION_NAME', 'test-collection')
        monkeypatch.setattr(utils, '_get_location_client', lambda: mock_client)

        result = utils.upsert_restaurant_geofences('r1', {'lat': 30.0, 'lon': -97.0})
        assert result is True
        call_kwargs = mock_client.batch_put_geofence.call_args[1]
        assert len(call_kwargs['Entries']) == 3

        geofence_ids = [e['GeofenceId'] for e in call_kwargs['Entries']]
        assert 'r1|5_MIN_OUT' in geofence_ids
        assert 'r1|PARKING' in geofence_ids
        assert 'r1|AT_DOOR' in geofence_ids

    def test_location_service_error_returns_false(self, monkeypatch):
        """Location service exception → returns False gracefully."""
        mock_client = MagicMock()
        mock_client.batch_put_geofence.side_effect = Exception("Service error")
        monkeypatch.setattr(utils, 'LOCATION_GEOFENCE_COLLECTION_NAME', 'test-collection')
        monkeypatch.setattr(utils, '_get_location_client', lambda: mock_client)

        result = utils.upsert_restaurant_geofences('r1', {'lat': 30.0, 'lon': -97.0})
        assert result is False


class TestDeleteRestaurantGeofences:
    def test_builds_correct_geofence_ids(self, monkeypatch):
        """Delete builds IDs for all 3 zones."""
        mock_client = MagicMock()
        mock_client.batch_delete_geofence.return_value = {'Errors': []}
        monkeypatch.setattr(utils, 'LOCATION_GEOFENCE_COLLECTION_NAME', 'test-collection')
        monkeypatch.setattr(utils, '_get_location_client', lambda: mock_client)

        result = utils.delete_restaurant_geofences('r1')
        assert result is True
        call_kwargs = mock_client.batch_delete_geofence.call_args[1]
        ids = call_kwargs['GeofenceIds']
        assert 'r1|5_MIN_OUT' in ids
        assert 'r1|PARKING' in ids
        assert 'r1|AT_DOOR' in ids

    def test_location_service_error_returns_false(self, monkeypatch):
        """Exception → returns False gracefully."""
        mock_client = MagicMock()
        mock_client.batch_delete_geofence.side_effect = Exception("Service error")
        monkeypatch.setattr(utils, 'LOCATION_GEOFENCE_COLLECTION_NAME', 'test-collection')
        monkeypatch.setattr(utils, '_get_location_client', lambda: mock_client)

        result = utils.delete_restaurant_geofences('r1')
        assert result is False

    def test_no_collection_returns_false(self, monkeypatch):
        """No collection configured → returns False."""
        monkeypatch.setattr(utils, 'LOCATION_GEOFENCE_COLLECTION_NAME', '')
        assert utils.delete_restaurant_geofences('r1') is False
