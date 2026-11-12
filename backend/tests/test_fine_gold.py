"""Fine-gold arithmetic (PRD §3 and Appendix A golden test case)."""

from decimal import Decimal

import pytest

from app.services.fine_gold import WeightError, fine_gold, split_weights, to_grams, validate_fineness

D = Decimal


@pytest.mark.parametrize(
    "net, ppt, expected",
    [
        ("96.000", "916", "87.936"),  # PRD Appendix A: 96 × 916 / 1000
        ("100.000", "916", "91.600"),  # PRD §3 example
        ("30.151", "995", "30.000"),  # 30.000245 rounds down
        ("31.284", "916", "28.656"),  # frontend J-1182 finished goods
        ("1.040", "750", "0.780"),
        ("0.001", "500", "0.001"),  # 0.0005 rounds half-up
        ("0.001", "499", "0.000"),
        ("10.000", "999.9", "9.999"),
    ],
)
def test_fine_gold_formula(net, ppt, expected):
    assert fine_gold(D(net), D(ppt)) == D(expected)


def test_prd_appendix_a_variance():
    issued = D("100.000")
    finished = fine_gold(D("96.000"), D("916"))
    scrap = D("10.000")
    variance = issued - finished - scrap
    assert variance == D("2.064")
    assert variance - D("1.500") == D("0.564")  # excess over allowance: a review flag, not proof of misconduct


def test_gross_net_are_separate():
    assert split_weights(D("31.500"), D("31.284")) == D("0.216")  # stones
    with pytest.raises(WeightError):
        split_weights(D("10.000"), D("10.001"))
    with pytest.raises(WeightError):
        split_weights(D("0"), D("0"))


@pytest.mark.parametrize("bad", ["1.0001", "abc", "nan", "inf"])
def test_weights_reject_bad_precision(bad):
    with pytest.raises(WeightError):
        to_grams(bad)


@pytest.mark.parametrize("bad", ["0", "-1", "1000", "999.95", "abc"])
def test_fineness_range(bad):
    with pytest.raises(WeightError):
        validate_fineness(bad)


def test_fineness_accepts_trade_values():
    assert validate_fineness(916) == D("916.0")
    assert validate_fineness("999.9") == D("999.9")
