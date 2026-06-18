from utils.progress import make_progress_bar


def test_progress_bar_zero():
    bar = make_progress_bar(0)
    assert "[□□□□□□□□□□] 0%" in bar


def test_progress_bar_hundred():
    bar = make_progress_bar(100)
    assert "[■■■■■■■■■■] 100%" in bar


def test_progress_bar_fifty():
    bar = make_progress_bar(50)
    assert "[■■■■■□□□□□] 50%" in bar


def test_progress_bar_clamps_above_100():
    bar = make_progress_bar(200)
    assert "[■■■■■■■■■■] 100%" in bar


def test_progress_bar_clamps_below_0():
    bar = make_progress_bar(-10)
    assert "[□□□□□□□□□□] 0%" in bar


def test_progress_bar_custom_blocks():
    bar = make_progress_bar(50, total_blocks=20)
    assert "[■■■■■■■■■■□□□□□□□□□□] 50%" in bar
