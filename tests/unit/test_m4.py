from src.m4_integration.quota import QuotaManager
from src.m4_integration.metrics import MetricsCollector

def test_m4_quota_enforcement():
    qm = QuotaManager(default_limit=1000)
    uid = 2001

    assert qm.check_quota(uid, 500) is True
    qm.update_usage(uid, 500)
    assert qm.get_quota(uid).used_bytes == 500

    # Boundary check: exact limit
    assert qm.check_quota(uid, 500) is True

    # Exceed limit by 1 byte
    assert qm.check_quota(uid, 501) is False

def test_m4_metrics_collector():
    mc = MetricsCollector()
    data = mc.get_dashboard_data()
    assert "disk_usage" in data
    assert "cache_hit_ratio" in data
    assert "fragmentation_pct" in data
