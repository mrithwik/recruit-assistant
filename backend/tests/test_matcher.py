from app.matching.matcher import score_to_tier
from app.models.enums import MatchTier


def test_score_to_tier_bands():
    assert score_to_tier(90, has_red_flag=False) == MatchTier.GREAT
    assert score_to_tier(85, has_red_flag=False) == MatchTier.GREAT
    assert score_to_tier(75, has_red_flag=False) == MatchTier.GOOD
    assert score_to_tier(70, has_red_flag=False) == MatchTier.GOOD
    assert score_to_tier(60, has_red_flag=False) == MatchTier.AVERAGE
    assert score_to_tier(50, has_red_flag=False) == MatchTier.AVERAGE
    assert score_to_tier(20, has_red_flag=False) == MatchTier.POOR


def test_red_flag_overrides_score():
    assert score_to_tier(95, has_red_flag=True) == MatchTier.RED_FLAG
