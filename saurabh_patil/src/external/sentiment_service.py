import random
import logging
from typing import Tuple
from src.utils.exceptions import EmptyCommentError, SentimentServiceError

logger = logging.getLogger(__name__)

# Sentiment keyword config — extend here when adding new patterns
POSITIVE_KEYWORDS: Tuple[str, ...] = ("amazing", "delicious")
NEGATIVE_KEYWORDS: Tuple[str, ...] = ("terrible", "never coming back")
NEUTRAL_KEYWORDS:  Tuple[str, ...] = ("okay",)

POSITIVE_SCORE  =  0.95
NEGATIVE_SCORE  = -0.95
NEUTRAL_SCORE   =  0.0
CHAOS_RATE      =  0.01   # probability of simulated infrastructure failure


class SentimentService:
    """
    Mock sentiment analysis service.

    Replicates the interface you'd use against a real provider (AWS Comprehend,
    Google NLP, etc.) so the application layer never needs to change on swap-out.

    Includes a ``CHAOS_RATE`` failure to validate graceful-degradation paths.
    """

    def __init__(self):
        self.api_url = "https://mock-sentiment-api.jivaha.com/analyze"

    async def analyze_text(self, text: str) -> Tuple[str, float]:
        """
        Classify ``text`` into a sentiment label and confidence score.

        Args:
            text: The review comment to analyse. Must be non-empty.

        Returns:
            A ``(label, score)`` tuple where:
            - ``label`` is one of ``"positive"``, ``"negative"``, ``"neutral"``
            - ``score`` is a float in ``[-1.0, 1.0]``

        Raises:
            EmptyCommentError:      If ``text`` is an empty string.
            SentimentServiceError:  On simulated infrastructure failure (probability=CHAOS_RATE).

        Example:
            >>> label, score = await svc.analyze_text("Amazing pizza!")
            >>> label
            'positive'
            >>> score
            0.95
        """
        if text == "":
            raise EmptyCommentError()

        if random.random() < CHAOS_RATE:
            raise SentimentServiceError("Chaos monkey triggered a random service failure")

        t = text.lower()
        if any(kw in t for kw in POSITIVE_KEYWORDS):
            return "positive", POSITIVE_SCORE
        if any(kw in t for kw in NEGATIVE_KEYWORDS):
            return "negative", NEGATIVE_SCORE
        if any(kw in t for kw in NEUTRAL_KEYWORDS):
            return "neutral", NEUTRAL_SCORE
        return "neutral", NEUTRAL_SCORE