import json
import time

import asyncio
import httpx
from scripts import demo_server
from scripts.mobile_auth import MobileStore
from sensor_simulator.run import make_payload


class LocalClient:
    def __init__(self, app):
        self.app = app

    def post(self, *args, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver') as client:
                return await client.post(*args, **kwargs)
        return asyncio.run(send())


def test_ingest_contract_and_persistence(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / 'auth.sqlite3', tmp_path / 'data', 'invite-code')
    monkeypatch.setattr(demo_server, 'MOBILE', mobile)
    alice = mobile.register('sensor_alice', 'correct-horse-1', 'correct-horse-1', 'invite-code')
    bob = mobile.register('sensor_bob', 'correct-horse-2', 'correct-horse-2', 'invite-code')
    workout_id, workout_path = mobile.create_workout(alice['id'])
    (workout_path / 'result.json').write_text('{"camera_score": 82}')
    pairing = mobile.create_pairing(alice['id'], 'esp32-demo-01', workout_id=workout_id)
    client = LocalClient(demo_server.app)
    url = '/api/sensor/ingest'
    headers = {'Authorization': 'Bearer ' + pairing['token']}
    payload = make_payload('esp32-demo-01', 1)
    assert client.post(url, json=payload, headers=headers).status_code == 200
    assert client.post(url, json=make_payload('esp32-demo-01', 3), headers=headers).json()['missing_sequences'] == 1
    assert client.post(url, json=payload, headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert client.post(url, content=b'{bad', headers=headers).status_code == 400
    assert client.post(url, content=b' ' * 65537, headers=headers).status_code == 413
    assert client.post(url, json={**payload, 'channels': payload['channels'][:-1]}, headers=headers).status_code == 400
    assert mobile.sensor_status(bob['id']) == []
    restarted = MobileStore(mobile.db_path, mobile.data_dir, 'invite-code')
    assert restarted.sensor_status(alice['id'])[0]['last_sequence'] == 3
    with restarted.connect() as db:
        rows = db.execute('SELECT device_id, sequence, device_time_ms, received_at, user_id, workout_id, channels_json FROM sensor_samples ORDER BY sequence').fetchall()
    assert len(rows) == 2 and rows[0]['user_id'] == alice['id']
    assert rows[0]['workout_id'] == workout_id
    assert (workout_path / 'result.json').read_text() == '{"camera_score": 82}'
    assert len(json.loads(rows[0]['channels_json'])) == 16


def test_ingest_rate_limit(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / 'auth.sqlite3', tmp_path / 'data', 'invite-code')
    monkeypatch.setattr(demo_server, 'MOBILE', mobile)
    user = mobile.register('sensor_user', 'correct-horse-1', 'correct-horse-1', 'invite-code')
    pairing = mobile.create_pairing(user['id'], 'esp32-demo-01')
    headers = {'Authorization': 'Bearer ' + pairing['token']}
    client = LocalClient(demo_server.app)
    for sequence in range(1, 241):
        assert client.post('/api/sensor/ingest', json=make_payload('esp32-demo-01', sequence), headers=headers).status_code == 200
    assert client.post('/api/sensor/ingest', json=make_payload('esp32-demo-01', 241), headers=headers).status_code == 429


def test_ingest_accepts_fresh_token_and_rejects_old_expired_revoked_and_unknown(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / 'auth.sqlite3', tmp_path / 'data', 'invite-code')
    monkeypatch.setattr(demo_server, 'MOBILE', mobile)
    user = mobile.register('sensor_user', 'correct-horse-1', 'correct-horse-1', 'invite-code')
    client = LocalClient(demo_server.app)
    url = '/api/sensor/ingest'
    payload = make_payload('esp32-demo-01', 1)

    first = mobile.create_pairing(user['id'], 'esp32-demo-01')
    assert client.post(url, json=payload, headers={'Authorization': 'Bearer ' + first['token']}).status_code == 200

    second = mobile.create_pairing(user['id'], 'esp32-demo-01')
    assert client.post(url, json=payload, headers={'Authorization': 'Bearer ' + first['token']}).status_code == 401
    # A fresh pairing can restart device sequencing while old samples survive.
    assert client.post(url, json=payload, headers={'Authorization': 'Bearer ' + second['token']}).status_code == 200
    assert mobile.sensor_status(user['id'])[0]['last_sequence'] == 1

    with mobile.connect() as db:
        db.execute('UPDATE sensor_pairings SET expires_at=? WHERE id=?', (int(time.time()) - 1, second['pairing_id']))
    assert client.post(url, json=make_payload('esp32-demo-01', 3), headers={'Authorization': 'Bearer ' + second['token']}).status_code == 401

    third = mobile.create_pairing(user['id'], 'esp32-demo-01')
    mobile.revoke_pairing(third['pairing_id'], user['id'])
    assert client.post(url, json=make_payload('esp32-demo-01', 3), headers={'Authorization': 'Bearer ' + third['token']}).status_code == 401
    assert client.post(url, json=payload, headers={'Authorization': 'Bearer arbitrary'}).status_code == 401


def test_esp32_baseline_is_returned_with_delta(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / 'auth.sqlite3', tmp_path / 'data', 'invite-code')
    monkeypatch.setattr(demo_server, 'MOBILE', mobile)
    user = mobile.register('sensor_delta', 'correct-horse-1', 'correct-horse-1', 'invite-code')
    pairing = mobile.create_pairing(user['id'], 'esp32-demo-01')
    client = LocalClient(demo_server.app)
    payload = make_payload('esp32-demo-01', 1)
    payload['baseline'] = {f'channel_{i}': 1100 for i in range(16)}
    payload['baseline']['channel_8'] = 1112
    payload['channels'][8]['raw_value'] = 1051
    assert client.post('/api/sensors/telemetry', json=payload,
                       headers={'Authorization': 'Bearer ' + pairing['token']}).status_code == 200
    device = MobileStore(mobile.db_path, mobile.data_dir, 'invite-code').sensor_status(user['id'])[0]
    assert device['sequence'] == 1
    assert device['baseline']['channel_8'] == 1112
    assert device['channels'][8] == {'channel_id': 'channel_8', 'raw_value': 1051, 'delta': 61, 'hand': True}
    assert device['received_at']


def test_restarted_sequence_and_exact_retry_are_accepted(tmp_path, monkeypatch):
    mobile = MobileStore(tmp_path / 'auth.sqlite3', tmp_path / 'data', 'invite-code')
    monkeypatch.setattr(demo_server, 'MOBILE', mobile)
    user = mobile.register('sensor_reset', 'correct-horse-1', 'correct-horse-1', 'invite-code')
    pairing = mobile.create_pairing(user['id'], 'esp32-demo-01')
    client = LocalClient(demo_server.app)
    headers = {'Authorization': 'Bearer ' + pairing['token']}
    url = '/api/sensor/ingest'

    first = client.post(url, json=make_payload('esp32-demo-01', 10), headers=headers)
    lower = client.post(url, json=make_payload('esp32-demo-01', 5), headers=headers)
    later = client.post(url, json=make_payload('esp32-demo-01', 11), headers=headers)
    retry = client.post(url, json=make_payload('esp32-demo-01', 11), headers=headers)
    restarted = client.post(url, json=make_payload('esp32-demo-01', 1), headers=headers)

    assert [response.status_code for response in (first, lower, later, retry, restarted)] == [200] * 5
    assert lower.json()['out_of_order'] is True
    assert later.json()['out_of_order'] is False
    assert retry.json()['duplicate'] is True
    assert restarted.json()['out_of_order'] is True
    with mobile.connect() as db:
        rows = db.execute('SELECT sequence,device_sequence FROM sensor_samples ORDER BY sequence').fetchall()
    assert [(row['sequence'], row['device_sequence']) for row in rows] == [(1, 10), (2, 5), (3, 11), (4, 1)]
    status = mobile.sensor_status(user['id'])[0]
    assert status['last_sequence'] == 1
    assert status['sample_sequence'] == 4
