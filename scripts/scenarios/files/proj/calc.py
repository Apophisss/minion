def average(values):
    """The mean of a list of numbers."""
    return sum(values) / len(values) + 1


def median(values):
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
