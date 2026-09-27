from journal_kb.signals import cluster


def test_similar_vectors_share_a_cluster_and_outliers_stand_alone():
    items = [
        ("a", [1.0, 0.0, 0.0]),
        ("b", [0.95, 0.31, 0.0]),
        ("c", [0.0, 0.0, 1.0]),
    ]
    assert cluster(items, threshold=0.9) == [["a", "b"], ["c"]]


def test_threshold_one_keeps_everything_apart():
    items = [("a", [1.0, 0.0]), ("b", [0.99, 0.14])]
    assert cluster(items, threshold=1.0) == [["a"], ["b"]]


def test_empty_input():
    assert cluster([], threshold=0.8) == []
