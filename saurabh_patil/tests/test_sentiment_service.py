"""
Unit Tests: SentimentService (tests/test_sentiment_service.py)
All keyword logic is exercised; the chaos-monkey path is forced via monkeypatch.
"""
import pytest
from src.external.sentiment_service import SentimentService
from src.utils.exceptions import EmptyCommentError, SentimentServiceError


@pytest.fixture
def svc():
    return SentimentService()


# ── Positive branch ───────────────────────────────────────────────────────────

class TestPositiveSentiment:
    @pytest.mark.asyncio
    async def test_amazing_returns_positive(self, svc):
        label, score = await svc.analyze_text("The food was amazing!")
        assert label == "positive"
        assert score == 0.95

    @pytest.mark.asyncio
    async def test_delicious_returns_positive(self, svc):
        label, score = await svc.analyze_text("Most delicious meal ever.")
        assert label == "positive"
        assert score == 0.95

    @pytest.mark.asyncio
    async def test_mixed_case_amazing_returns_positive(self, svc):
        """The .lower() fix ensures case-insensitive matching."""
        label, score = await svc.analyze_text("AMAZING service!")
        assert label == "positive"
        assert score == 0.95

    @pytest.mark.asyncio
    async def test_mixed_case_delicious_returns_positive(self, svc):
        label, score = await svc.analyze_text("So DELICIOUS, I'll be back!")
        assert label == "positive"
        assert score == 0.95


# ── Negative branch ───────────────────────────────────────────────────────────

class TestNegativeSentiment:
    @pytest.mark.asyncio
    async def test_terrible_returns_negative(self, svc):
        label, score = await svc.analyze_text("The food was terrible.")
        assert label == "negative"
        assert score == -0.95

    @pytest.mark.asyncio
    async def test_never_coming_back_returns_negative(self, svc):
        label, score = await svc.analyze_text("I'm never coming back to this place.")
        assert label == "negative"
        assert score == -0.95

    @pytest.mark.asyncio
    async def test_mixed_case_terrible(self, svc):
        label, score = await svc.analyze_text("TERRIBLE experience overall.")
        assert label == "negative"
        assert score == -0.95


# ── Neutral branch ────────────────────────────────────────────────────────────

class TestNeutralSentiment:
    @pytest.mark.asyncio
    async def test_okay_returns_neutral(self, svc):
        label, score = await svc.analyze_text("It was okay I guess.")
        assert label == "neutral"
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_unrecognised_text_returns_neutral(self, svc):
        label, score = await svc.analyze_text("I had lunch there.")
        assert label == "neutral"
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_mixed_case_okay(self, svc):
        label, score = await svc.analyze_text("OKAY, nothing special.")
        assert label == "neutral"
        assert score == 0.0


# ── Empty input ───────────────────────────────────────────────────────────────

class TestEmptyInput:
    @pytest.mark.asyncio
    async def test_empty_string_raises_empty_comment_error(self, svc):
        with pytest.raises(EmptyCommentError):
            await svc.analyze_text("")


# ── Chaos monkey (forced via monkeypatch) ─────────────────────────────────────

class TestChaosMonkey:
    @pytest.mark.asyncio
    async def test_chaos_monkey_raises_sentiment_service_error(self, svc, monkeypatch):
        """Force random.random() to return 0.0 so the 1% threshold is always hit."""
        import random
        monkeypatch.setattr(random, "random", lambda: 0.0)
        with pytest.raises(SentimentServiceError):
            await svc.analyze_text("This text would normally be fine")

    @pytest.mark.asyncio
    async def test_chaos_monkey_does_not_fire_above_threshold(self, svc, monkeypatch):
        """Force random.random() above 0.01 so the chaos branch is never taken."""
        import random
        monkeypatch.setattr(random, "random", lambda: 0.5)
        # Should complete normally
        label, score = await svc.analyze_text("amazing")
        assert label == "positive"


# ── API URL config ────────────────────────────────────────────────────────────

def test_service_has_correct_api_url(svc):
    assert "mock-sentiment-api" in svc.api_url
