from ace_api.engine.graders import grade


def test_mcq():
    p = {"correct_index": 2}
    assert grade("mcq", p, {"index": 2})
    assert not grade("mcq", p, {"index": 0})
    assert not grade("mcq", p, {})  # malformed answer never crashes


def test_tf():
    assert grade("tf", {"answer": True}, {"value": True})
    assert not grade("tf", {"answer": True}, {"value": False})


def test_gap_normalization():
    p = {"answers": ["Know-Your-Client", "KYC"]}
    assert grade("gap", p, {"text": "know your client"})
    assert grade("gap", p, {"text": "  KYC. "})
    assert not grade("gap", p, {"text": "know your product"})


def test_match_order_independent():
    p = {"pairs": [[0, 1], [1, 0]]}
    assert grade("match", p, {"pairs": [[1, 0], [0, 1]]})
    assert not grade("match", p, {"pairs": [[0, 0], [1, 1]]})


def test_numeric_absolute_tolerance():
    assert grade("numeric", {"answer": 100.0, "tolerance": 0.5}, {"value": 100.4})
    assert not grade("numeric", {"answer": 100.0, "tolerance": 0.5}, {"value": 101.0})
    assert grade("numeric", {"answer": 42.0}, {"value": 42})  # missing tolerance → exact
    assert not grade("numeric", {"answer": 42.0, "tolerance": 0.1}, {"value": "not-a-number"})
