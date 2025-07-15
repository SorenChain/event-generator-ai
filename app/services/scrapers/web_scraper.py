"""
Web Scraper Service for prediction market app.

This module provides functionality to scrape and clean web content
for use in prediction market events.
"""
import re
import string
import logging
from typing import Optional

import nltk
from nltk.corpus import stopwords
from langchain_community.document_loaders import WebBaseLoader
from app.config.settings import USER_AGENT  # Import USER_AGENT from settings

# Configure logging
logger = logging.getLogger(__name__)

# Ensure NLTK data is downloaded
nltk.download('stopwords', quiet=True)

def clean_text(text: str) -> str:
    """
    Clean text by removing special characters, extra whitespace, and stopwords.
    
    Args:
        text: Input text to clean
        
    Returns:
        Cleaned text
    """
    # Remove special characters and make lowercase
    translator = str.maketrans('', '', string.punctuation)
    cleaned_text = text.translate(translator).lower()
    
    # Remove extra whitespace
    cleaned_text = ' '.join(cleaned_text.split())
    
    # Remove stopwords
    stop_words = set(stopwords.words('english'))
    cleaned_words = [word for word in cleaned_text.split() if word not in stop_words]
    
    # Join words back into a cleaned string
    cleaned_text = ' '.join(cleaned_words)
    
    return cleaned_text

async def document_loader(url: str, word_limit: int = 1000) -> Optional[str]:
    """
    Load and clean document content from a URL with word limit.
    
    Args:
        url: The URL to load content from
        word_limit: Maximum number of words to return
        
    Returns:
        Cleaned and processed text content within word limit or None
    """
    # Check if URL contains reddit
    if re.search(r'reddit\.com|redd\.it', url, re.IGNORECASE):
        logger.info(f"Skipping Reddit URL: {url}")
        return None

    text_parts = []
    word_count = 0
    
    try:
        # USER_AGENT is now imported from settings
        loader = WebBaseLoader(url)
        
        async for doc in loader.alazy_load():
            sentences = doc.page_content.splitlines()
            
            for sentence in sentences:
                if sentence.strip():
                    cleaned_sentence = clean_text(sentence.strip())
                    sentence_words = len(cleaned_sentence.split())
                    
                    # Check if adding this sentence exceeds word limit
                    if word_count + sentence_words <= word_limit:
                        text_parts.append(cleaned_sentence)
                        word_count += sentence_words
                    else:
                        final_text = " ".join(text_parts)
                        # Check if total words are less than 50
                        if len(final_text.split()) < 50:
                            logger.info(f"Content too short from {url}: {len(final_text.split())} words")
                            return None
                        return final_text

        final_text = " ".join(text_parts)
        # Check if total words are less than 50
        if len(final_text.split()) < 50:
            logger.info(f"Content too short from {url}: {len(final_text.split())} words")
            return None
            
        return final_text
    
    except Exception as e:
        logger.error(f"Error scraping URL {url}: {e}")
        return None