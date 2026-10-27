from app.ml.baseline import BaselineLearner


def test_baseline_reports_mean_std_and_ema_from_normal_readings():
    baseline = BaselineLearner(required_readings=2)
    baseline.observe("S01", 10.0)
    status = baseline.observe("S01", 20.0)

    assert status.ready is True
    assert status.mean == 15.0
    assert status.std == 5.0
    assert status.ema_fast == 13.0
    assert status.ema_slow == 10.5
