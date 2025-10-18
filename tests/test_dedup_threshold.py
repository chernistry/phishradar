from app.dedup import is_duplicate


def test_threshold_boundary_notes():
    assert is_duplicate(1.0) is True
    assert is_duplicate(0.0) is False
    # With default 0.12 threshold, 0.88 should be duplicate
    assert is_duplicate(0.88) is True

