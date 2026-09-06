from app.hakim.run_android_sovereign import _background_test_evaluate


def test_background_survival_passes_with_continuous_heartbeat():
    state = {
        'test_id': 't1',
        'status': 'completed',
        'started_at': 1000.0,
        'expected_end_at': 1300.0,
        'seconds': 300,
        'interval': 5,
    }
    beats = [1000.0 + i * 5 for i in range(61)]
    result = _background_test_evaluate(state, beats, now=1301.0)
    assert result['status'] == 'PASS'
    assert result['heartbeat_count'] == 61
    assert result['max_gap_seconds'] == 5.0


def test_background_survival_fails_on_large_gap():
    state = {
        'test_id': 't2',
        'status': 'completed',
        'started_at': 1000.0,
        'expected_end_at': 1300.0,
        'seconds': 300,
        'interval': 5,
    }
    beats = [1000.0 + i * 5 for i in range(31)] + [1200.0 + i * 5 for i in range(21)]
    result = _background_test_evaluate(state, beats, now=1301.0)
    assert result['status'] == 'FAIL'
    assert result['max_gap_seconds'] > 30


def test_background_survival_fails_if_worker_disappears_after_grace():
    state = {
        'test_id': 't3',
        'status': 'running',
        'started_at': 1000.0,
        'expected_end_at': 1300.0,
        'seconds': 300,
        'interval': 5,
    }
    beats = [1000.0, 1005.0, 1010.0]
    result = _background_test_evaluate(state, beats, now=1400.0)
    assert result['status'] == 'FAIL'
    assert 'did not complete' in result['reason']


def test_background_survival_reports_in_progress_before_deadline():
    state = {
        'test_id': 't4',
        'status': 'running',
        'started_at': 1000.0,
        'expected_end_at': 1300.0,
        'seconds': 300,
        'interval': 5,
    }
    result = _background_test_evaluate(state, [1000.0, 1005.0], now=1100.0)
    assert result['status'] == 'IN_PROGRESS'
