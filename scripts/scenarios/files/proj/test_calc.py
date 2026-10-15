from calc import average, median


def test_average():
    assert average([2, 4, 6]) == 4


def test_median():
    assert median([5, 1, 3]) == 3
    assert median([4, 1, 3, 2]) == 2.5
