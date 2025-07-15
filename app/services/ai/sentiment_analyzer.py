"""
Sentiment Analysis Service.

This module provides functionality to analyze sentiment in text
for prediction market events.
"""
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple

import nltk
from nltk.tokenize import sent_tokenize
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Configure logging
logger = logging.getLogger(__name__)

# Ensure NLTK sentence tokenizer is available
nltk.download('punkt', quiet=True)

class SentimentAnalyzerService:
    """Service for analyzing sentiment in text."""
    
    @staticmethod
    async def analyze_sentence(sentence: str, sentiment_analyzer: SentimentIntensityAnalyzer) -> Tuple[float, str]:
        """
        Analyze the sentiment of a single sentence asynchronously.
        
        Args:
            sentence: Text to analyze
            sentiment_analyzer: VADER sentiment analyzer instance
            
        Returns:
            Tuple of (compound_score, sentence)
        """
        try:
            sentiment_dict = sentiment_analyzer.polarity_scores(sentence)
            return sentiment_dict['compound'], sentence
        except Exception as e:
            logger.error(f"Error analyzing sentence: {e}")
            return 0, sentence  # Default polarity of 0 for error cases
    
    @classmethod
    async def analyze_document(cls, document: str) -> Optional[str]:
        """
        Analyze the overall sentiment of a document.
        
        Args:
            document: Text to analyze
            
        Returns:
            Sentiment classification as 'Positive', 'Negative', or 'Neutral'
        """
        try:
            # Creating a SentimentIntensityAnalyzer object
            sentiment_analyzer = SentimentIntensityAnalyzer()
            
            # Split document into sentences
            sentences = sent_tokenize(document)
            
            # Create async tasks for analyzing each sentence
            tasks = [cls.analyze_sentence(sentence, sentiment_analyzer) for sentence in sentences]
            results = await asyncio.gather(*tasks)
            
            # Extract polarity scores and sentences
            polarity = [result[0] for result in results]
            processed_sentences = [result[1] for result in results]
            
            positive_sentences = [sentence for score, sentence in zip(polarity, processed_sentences) if score > 0.05]
            negative_sentences = [sentence for score, sentence in zip(polarity, processed_sentences) if score < -0.05]
            neutral_sentences = [sentence for score, sentence in zip(polarity, processed_sentences) if -0.05 <= score <= 0.05]
            
            avg_polarity = sum(polarity) / len(polarity) if polarity else 0
            
            sentiment_analysis_result = {
                'average_polarity': avg_polarity,
                'positive_sentences': positive_sentences,
                'negative_sentences': negative_sentences,
                'neutral_sentences': neutral_sentences,
                'most_positive_sentence': processed_sentences[polarity.index(max(polarity))] if positive_sentences else None,
                'most_negative_sentence': processed_sentences[polarity.index(min(polarity))] if negative_sentences else None,
                'document_sentiment': "Positive" if avg_polarity > 0.05 else "Negative" if avg_polarity < -0.05 else "Neutral"
            }
            
            return sentiment_analysis_result['document_sentiment']
        
        except Exception as e:
            logger.error(f"Error analyzing document sentiment: {e}")
            return None

# Alias function for backward compatibility
async def analyze_document(*args, **kwargs):
    """Backward compatibility function for analyze_document."""
    return await SentimentAnalyzerService.analyze_document(*args, **kwargs)