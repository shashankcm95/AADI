import json

import geofence_resync_worker as worker
import utils as _utils


def _queue_event(payload):
    return {
        'Records': [
            {
                'body': json.dumps(payload),
            }
        ]
    }


def test_worker_completes_single_batch_job(mock_tables, monkeypatch):
    class _NoopSQS:
        def send_message(self, QueueUrl, MessageBody):
            raise AssertionError('send_message should not be called when scan completes in one batch')

    monkeypatch.setattr(worker, 'config_table', mock_tables['config'])
    monkeypatch.setattr(worker, 'restaurants_table', mock_tables['restaurants'])
    monkeypatch.setattr(worker, 'GEOFENCE_RESYNC_BATCH_SIZE', 50)
    monkeypatch.setattr(worker, 'upsert_restaurant_geofences', lambda _id, _loc: True)
    monkeypatch.setattr(_utils, '_sqs_client', _NoopSQS())

    response = worker.lambda_handler(_queue_event({'task_type': 'geofence_resync', 'job_id': 'job-1'}), None)
    assert response['statusCode'] == 200

    global_item = mock_tables['config'].get_item(Key={'restaurant_id': '__GLOBAL__'})['Item']
    sync = global_item['geofence_sync']
    assert sync['job_id'] == 'job-1'
    assert sync['status'] == 'COMPLETED'
    assert sync['attempted'] == 3
    assert sync['updated'] == 3
    assert sync['failed'] == 0
    assert sync['batches_processed'] == 1


def test_worker_enqueues_follow_up_when_scan_has_more_pages(mock_tables, monkeypatch):
    sent_messages = []

    class _FakeSQS:
        def send_message(self, QueueUrl, MessageBody):
            sent_messages.append({
                'QueueUrl': QueueUrl,
                'MessageBody': MessageBody,
            })
            return {'MessageId': 'msg-1'}

    monkeypatch.setattr(worker, 'config_table', mock_tables['config'])
    monkeypatch.setattr(worker, 'restaurants_table', mock_tables['restaurants'])
    monkeypatch.setattr(worker, 'GEOFENCE_RESYNC_BATCH_SIZE', 2)
    monkeypatch.setattr(worker, 'GEOFENCE_RESYNC_QUEUE_URL', 'https://sqs.us-east-1.amazonaws.com/123/geofence-resync')
    monkeypatch.setattr(worker, 'upsert_restaurant_geofences', lambda _id, _loc: True)
    monkeypatch.setattr(_utils, '_sqs_client', _FakeSQS())

    response = worker.lambda_handler(_queue_event({'task_type': 'geofence_resync', 'job_id': 'job-2'}), None)
    assert response['statusCode'] == 200

    global_item = mock_tables['config'].get_item(Key={'restaurant_id': '__GLOBAL__'})['Item']
    sync = global_item['geofence_sync']
    assert sync['job_id'] == 'job-2'
    assert sync['status'] == 'IN_PROGRESS'
    assert sync['attempted'] == 2
    assert sync['updated'] == 2
    assert sync['failed'] == 0
    assert sync['batches_processed'] == 1

    assert len(sent_messages) == 1
    payload = json.loads(sent_messages[0]['MessageBody'])
    assert payload['task_type'] == 'geofence_resync'
    assert payload['job_id'] == 'job-2'
    assert isinstance(payload.get('cursor'), dict)


def test_worker_retries_geofence_upsert_before_counting_failure(mock_tables, monkeypatch):
    attempts = {'count': 0}

    def _flaky_upsert(_restaurant_id, _location):
        attempts['count'] += 1
        return attempts['count'] >= 3

    mock_tables['restaurants'].items = {
        'r1': {'restaurant_id': 'r1', 'name': 'R1', 'location': {'lat': 12.0, 'lon': -86.0}},
    }

    monkeypatch.setattr(worker, 'config_table', mock_tables['config'])
    monkeypatch.setattr(worker, 'restaurants_table', mock_tables['restaurants'])
    monkeypatch.setattr(worker, 'GEOFENCE_RESYNC_BATCH_SIZE', 10)
    monkeypatch.setattr(worker, 'GEOFENCE_RESYNC_MAX_UPSERT_ATTEMPTS', 3)
    monkeypatch.setattr(worker, 'upsert_restaurant_geofences', _flaky_upsert)

    response = worker.lambda_handler(_queue_event({'task_type': 'geofence_resync', 'job_id': 'job-3'}), None)
    assert response['statusCode'] == 200

    global_item = mock_tables['config'].get_item(Key={'restaurant_id': '__GLOBAL__'})['Item']
    sync = global_item['geofence_sync']
    assert sync['job_id'] == 'job-3'
    assert sync['status'] == 'COMPLETED'
    assert sync['attempted'] == 1
    assert sync['updated'] == 1
    assert sync['failed'] == 0
    assert attempts['count'] == 3
