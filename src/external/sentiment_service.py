import random
import logging
from typing import Tuple
from src.utils.exceptions import EmptyCommentError, SentimentServiceError

logger = logging.getLogger(__name__)

class SentimentService:
    def __init__(self):
        self.api_url = "https://mock-sentiment-api.jivaha.com/analyze"

    async def analyze_text(self, text: str) -> Tuple[str, float]:
        if text == "":
            raise EmptyCommentError()

        # Chaos monkey check
        if random.random() < 0.01:
            raise SentimentServiceError("Chaos monkey triggered a random service failure")

        t = text.lower()
        if "amazing" in t or "delicious" in t:
            return "positive", 0.95
        elif "terrible" in t or "never coming back" in t:
            return "negative", -0.95
        elif "okay" in t:
            return "neutral", 0.0
        return "neutral", 0.0