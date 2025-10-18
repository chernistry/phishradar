from app.dedup import is_duplicate


def test_threshold_boundary_notes():
    # Cross-domain requires higher similarity
    assert is_duplicate(1.0, same_domain=False) is True
    assert is_duplicate(0.98, same_domain=False) is False  # default global floor 0.985
    # Same-domain allows slightly lower floor
    assert is_duplicate(0.95, same_domain=True) is True
    assert is_duplicate(0.93, same_domain=True) is False
