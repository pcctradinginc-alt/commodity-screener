"""
FinBERT Sentiment Analyzer – ersetzt Keyword-Scoring
"""

from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
import os

class FinBertSentiment:
    def __init__(self):
        model_name = "ProsusAI/finbert"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()
        print("  ✅ FinBERT Sentiment Model geladen")

    def get_sentiment(self, text: str):
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            outputs = self.model(**inputs)
            scores = torch.nn.functional.softmax(outputs.logits, dim=1)
        
        # 0 = negative, 1 = neutral, 2 = positive
        positive = scores[0][2].item()
        neutral = scores[0][1].item()
        negative = scores[0][0].item()

        if positive > 0.6:
            return "bullish", round(positive, 3)
        elif negative > 0.6:
            return "bearish", round(negative, 3)
        else:
            return "neutral", round(neutral, 3)
