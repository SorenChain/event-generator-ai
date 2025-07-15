"""
Date utilities for the prediction market app.
"""
import re
import logging
from datetime import datetime
from typing import Optional

from langchain_openai import ChatOpenAI
from app.config.settings import OPENAI_API_KEY, DEFAULT_MODEL

# Configure logging
logger = logging.getLogger(__name__)

# Initialize the OpenAI model
openai_model = ChatOpenAI(api_key=OPENAI_API_KEY, model=DEFAULT_MODEL)

def parse_date(text: str) -> Optional[datetime]:
    """
    Parse a date from text using multiple formats.
    
    Args:
        text: Text containing a date
        
    Returns:
        Datetime object or None if parsing fails
    """
    try:
        # Clean the input text
        text = text.strip()
        # Remove any parentheses and their contents
        text = re.sub(r'\([^)]*\)', '', text)
        
        # Common date formats to try
        date_formats = [
            "%Y-%m-%d",           # 2025-07-31
            "%B %d, %Y",          # July 31, 2025
            "%d %B %Y",           # 31 July 2025
            "%B, %Y",             # July, 2025
            "%Y/%m/%d",           # 2025/07/31
            "%d/%m/%Y",           # 31/07/2025
            "%d-%m-%Y",           # 31-07-2025
            "%Y.%m.%d",           # 2025.07.31
            "%d.%m.%Y",           # 31.07.2025
            "%Y %B %d",           # 2025 July 31
            "%b %d, %Y",          # Jul 31, 2025
            "%d %b %Y",           # 31 Jul 2025
        ]
        
        # First try to find any date-like patterns in the text
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',                    # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',                    # DD/MM/YYYY
            r'\d{4}/\d{2}/\d{2}',                    # YYYY/MM/DD
            r'[A-Za-z]+\s+\d{1,2},\s+\d{4}',        # Month DD, YYYY
            r'\d{1,2}\s+[A-Za-z]+\s+\d{4}',         # DD Month YYYY
            r'[A-Za-z]+,\s+\d{4}',                   # Month, YYYY
            r'\d{4}\s+[A-Za-z]+\s+\d{1,2}',         # YYYY Month DD
        ]
        
        # Try to find a date pattern in the text
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group()
                # Try parsing with each format
                for date_format in date_formats:
                    try:
                        return datetime.strptime(date_str, date_format)
                    except ValueError:
                        continue
                        
        # If no pattern matched, try direct parsing with formats
        for date_format in date_formats:
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                continue
                
        return None
    except Exception as e:
        logger.error(f"Error parsing date: {e}")
        return None

# async def get_date_time_from_snippet(snippet: str) -> str:
#     """
#     Get the date and time from a snippet using LLM and a prompt in ISO format.
    
#     Args:
#         snippet (str): The snippet to extract date and time from
        
#     Returns:
#         str: Extracted date and time in ISO format (YYYY-MM-DD HH:MM:SS) or None if not found
#     """
#     # Get the current date for reference
#     current_date = datetime.now().isoformat()

#     # Refined prompt to ensure the LLM returns only the datetime or "None"
#     prompt = (
#         f"As of today ({current_date}), extract the date and time from the following snippet. "
#         f"Return only the datetime in ISO format (YYYY-MM-DD HH:MM:SS) if found, or 'None' if no valid datetime exists.\n\n"
#         f"Snippet: {snippet}\n\n"
#         f"Output (strictly in format YYYY-MM-DD HH:MM:SS or 'None'):"
#     )

#     # Invoke the LLM with the prompt
#     response = openai_model.invoke(prompt)
#     extracted_text = response.content.strip()

#     # Validate the response
#     if extracted_text.lower() == "none":
#         return None

#     # Check if the response matches the expected ISO format using regex
#     iso_pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
#     if re.match(iso_pattern, extracted_text):
#         try:
#             # Validate that it's a real datetime
#             datetime.strptime(extracted_text, "%Y-%m-%d %H:%M:%S")
#             return extracted_text
#         except ValueError:
#             return None

#     # If the format doesn't match or isn't valid, return None
#     return None


async def get_date_time_from_snippet(snippet: str) -> Optional[str]:
    """
    Extract date and time from a text snippet using LLM.
    
    Args:
        snippet: Text snippet to extract date from
        
    Returns:
        Date in ISO format or None
    """
    # Get the current date for reference
    current_date = datetime.now().isoformat()

    # Refined prompt to ensure the LLM returns only the datetime or "None"
    prompt = (
        f"As of today ({current_date}), extract the date and time from the following snippet. "
        f"Return only the datetime in ISO format (YYYY-MM-DD HH:MM:SS) if found, or 'None' if no valid datetime exists.\n\n"
        f"Snippet: {snippet}\n\n"
        f"Output (strictly in format YYYY-MM-DD HH:MM:SS or 'None'):"
    )

    try:
        # Invoke the LLM with the prompt
        response = openai_model.invoke(prompt)
        extracted_text = response.content.strip()

        # Validate the response
        if extracted_text.lower() == "none":
            return None

        # Check if the response matches the expected ISO format using regex
        iso_pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        if re.match(iso_pattern, extracted_text):
            try:
                # Validate that it's a real datetime
                datetime.strptime(extracted_text, "%Y-%m-%d %H:%M:%S")
                return extracted_text
            except ValueError:
                return None

        # If the format doesn't match or isn't valid, return None
        return None
    
    except Exception as e:
        logger.error(f"Error extracting date from snippet: {e}")
        return None