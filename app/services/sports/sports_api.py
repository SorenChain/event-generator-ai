"""
Sports API Service for prediction market app.

This module provides functionality to fetch sports data and generate
betting questions for sports events.
"""
import re
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

import requests
from app.config.settings import (
    ODDS_API_KEY, 
    DEFAULT_MODEL, 
    OPENAI_API_KEY,
    DEFAULT_RETRY_COUNT,
    DEFAULT_RETRY_DELAY
)
from app.utils.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_model = ChatOpenAI(api_key=OPENAI_API_KEY, model=DEFAULT_MODEL)

class SportsApiService:
    """Service for fetching sports data and generating betting questions."""
    
    def __init__(self, api_key: str = ODDS_API_KEY):
        """Initialize the Sports API Service."""
        self.api_key = api_key
        self.base_url = 'https://api.the-odds-api.com/v4'
    
    def fetch_sports_data(self) -> Dict[str, Any]:
        """Fetch sports categories and details from the-odds-api."""
        try:
            # Step 1: Fetch all available sports categories
            categories_url = f"{self.base_url}/sports/?apiKey={self.api_key}"
            categories_response = requests.get(categories_url)
            categories_response.raise_for_status()
            categories = categories_response.json()
            
            # Step 2: Create a dictionary to store all results
            results = {
                'categories': categories,
                'details': {}
            }
            
            # Step 3: Loop through each category and fetch its details
            for category in categories:
                sport_key = category['key']
                
                # Skip if key is not active
                if not category['active']:
                    logger.info(f"Skipping {sport_key} - not active")
                    continue
                
                try:
                    # Fetch details for this sport key
                    details_url = f"{self.base_url}/sports/{sport_key}/events?apiKey={self.api_key}"
                    details_response = requests.get(details_url)
                    details_response.raise_for_status()
                    
                    # Store the details in our results dictionary
                    results['details'][sport_key] = details_response.json()
                    
                    logger.info(f"Fetched details for {sport_key}")
                    
                    # Add a small delay to avoid hitting rate limits
                    time.sleep(0.2)
                    
                except requests.exceptions.RequestException as detail_error:
                    logger.error(f"Error fetching details for {sport_key}: {str(detail_error)}")
                    results['details'][sport_key] = {'error': str(detail_error)}
            
            return results
            
        except requests.exceptions.RequestException as error:
            logger.error(f"Error fetching sports data: {str(error)}")
            raise
    
    def organize_sports_events(self, results: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Organize sports events by topic, with each event having description and end date.
        
        Returns:
            Tuple of (organized_events, null_team_events)
        """
        organized_events = []
        null_team_events = []
        
        # Loop through each category
        for category in results['categories']:
            topic = category['key']
            
            # Check if we have details for this topic
            if topic in results['details']:
                # Get the events for this topic
                events = results['details'][topic]
                
                # Skip if there was an error fetching details
                if isinstance(events, dict) and 'error' in events:
                    logger.info(f"Skipping {topic} due to error in fetching details")
                    continue
                
                # Process each event
                for event in events:
                    # check if home and away team is None
                    if event.get('home_team') is None or event.get('away_team') is None:
                        null_team_event = {
                            'key': topic,
                            'topic': category['group'],
                            'title': category['title'],
                            'description': category['description'],
                            'event_id': event['id'],
                            'home_team': event.get('home_team'),
                            'away_team': event.get('away_team'),
                            'end_date': event['commence_time'],
                            'formatted_date': datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
                        }
                        null_team_events.append(null_team_event)
                    else:
                        # Create an organized event entry
                        organized_event = {
                            'key': topic,
                            'topic': category['group'],
                            'title': category['title'],
                            'description': category['description'],
                            'event_id': event['id'],
                            'event_description': f"{event['home_team']} vs {event['away_team']}",
                            'home_team': event['home_team'],
                            'away_team': event['away_team'],
                            'end_date': event['commence_time'],
                            # Optional: Convert to more readable date format
                            'formatted_date': datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
                        }
                        organized_events.append(organized_event)
        
        return organized_events, null_team_events
    
    @staticmethod
    async def generate_question_from_api(
        event_info: Dict[str, str], 
        sentiment: Dict[str, Any] = None, 
        max_retries: int = DEFAULT_RETRY_COUNT, 
        delay: int = DEFAULT_RETRY_DELAY
    ) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[str], Optional[str]]:
        """
        Generate a betting question from event information.
        
        Args:
            event_info: Dictionary containing event information
            sentiment: Optional sentiment information
            max_retries: Maximum number of retries
            delay: Delay between retries in seconds
            
        Returns:
            Tuple of (question, yes_probability, no_probability, end_date, event_description)
        """
        # Get current date for reference only
        current_date = datetime.now().date()
        
        # Extract event details from the event_info dictionary
        event_match = event_info['Event']
        end_date = event_info['End Date']
        
        # Parse the end date to a more readable format for the event description
        try:
            # Convert ISO format to datetime object
            parsed_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            # Format the date for display
            formatted_date = parsed_date.strftime('%B %d, %Y')
        except:
            # If date parsing fails, use the original
            formatted_date = end_date
        
        # Default sentiment if not provided
        if sentiment is None:
            sentiment = {"positive": 0.5, "negative": 0.5}
        
        prompt_template = """
        You are a betting application bot responsible for generating structured betting content for sports events using the provided information.

        INPUTS:
        - Topic: {topic}
        - Description: {description}
        - Event: {event}
        - End Date: {end_date}

        TASK:

        1. **Generate a betting question**:
        - Use specific names/entities from the event (never generic terms).
        - Make the question clear, concise (under 25 words), and outcome-focused.
        - Format the question as: "Will [Team A] win the [event type] game against [Team B] on [date]?"
        - Always phrase the question so the first team mentioned is the subject of the "Will" question.

        2. **Assign probabilities**:
        - Always use Yes/No format: "Yes: X%, No: Y%" (must total 100%)
        - "Yes" refers to the first team winning (the team that is the subject of the question)
        - "No" refers to the first team not winning (either the second team wins or another outcome)

        3. **Generate an event description** (MANDATORY):
        - Write 2–4 engaging, factual sentences based on the Topic, Description, Event and End Date.
        - Mention all key participants/entities.
        - Include the event type (from the description) and scheduled date in a readable format.
        - Make it sound exciting and informative.

        4. **Set the market resolution date**:
        - Use the provided end date in full UTC format (do not change format).

        RETURN FORMAT (strictly follow this structure):
        Generated Question: [your betting question]  
        Probability: Yes: X%, No: Y%  
        Market Resolution Date: {raw_end_date}  
        Event Description: [2–4 sentence engaging and factual description]

        Return "None" if:
        - Specific team or player names are missing.
        - Event lacks a clear, resolvable outcome.
        """

        for attempt in range(max_retries):
            try:
                # Format the prompt using the template
                prompt = PromptTemplate(template=prompt_template)
                message = prompt.format(
                    topic=event_info['Topic'],
                    description=event_info['Description'],
                    event=event_match,
                    end_date=formatted_date,
                    raw_end_date=end_date
                )
            except Exception as e:
                logger.exception("Error formatting prompt. Skipping attempt.")
                await asyncio.sleep(delay)
                continue

            try:
                # Send the request to OpenAI
                response = openai_model.invoke(message)
            except Exception as e:
                logger.exception("Error invoking OpenAI. Skipping attempt.")
                await asyncio.sleep(delay)
                continue

            try:
                # Parse the response
                data = response.content
                
                if 'Generated Question:' in data:
                    # Extract the question
                    start_index = data.find('Generated Question:') + len('Generated Question:')
                    end_index = data.find('Probability:') if 'Probability:' in data else len(data)
                    generated_question = data[start_index:end_index].strip()

                    # Ensure we capture the full question ending with a question mark
                    match_question = re.search(r'.*\?', generated_question)
                    if match_question:
                        generated_question = match_question.group(0)

                    # Extract the event description
                    if 'Event Description:' in data:
                        desc_start_index = data.find('Event Description:') + len('Event Description:')
                        event_description = data[desc_start_index:].strip()
                    else:
                        event_description = None
                        logger.warning("Event Description not found in response")
                    
                    # Extract the probability section
                    prob_index = data.find('Probability:')
                    
                    if prob_index != -1:
                        market_date_index = data.find('Market Resolution Date:') if 'Market Resolution Date:' in data else len(data)
                        probability_section = data[prob_index + len('Probability:'):market_date_index].strip()
                        
                        # Check for binary Yes/No format
                        binary_yes = re.search(r'Yes\s*:\s*(\d+)', probability_section)
                        binary_no = re.search(r'No\s*:\s*(\d+)', probability_section)

                        if binary_yes and binary_no:
                            yes_probability = int(binary_yes.group(1))
                            no_probability = int(binary_no.group(1))
                            if yes_probability + no_probability == 100 and 0 <= yes_probability <= 100:
                                return generated_question, yes_probability, no_probability, end_date, event_description
                        else:
                            logger.info(f"Expected Yes/No probabilities but got: {probability_section}")
                            return None, None, None, None, None
                    else:
                        logger.info("No probability section found in response.")
                    
                    # If we got here but have a question and description, return those with None for probability
                    if generated_question and event_description:
                        return generated_question, None, None, end_date, event_description
                    return None, None, None, None, None
                else:
                    logger.info("Failed to generate betting question and description.")
            except Exception as e:
                logger.exception(f"Error parsing response: {e}")

            logger.info(f"Retrying... ({attempt + 1}/{max_retries})")
            await asyncio.sleep(delay)

        return None, None, None, None, None  # If max retries are exceeded, return None

    @staticmethod
    async def generate_multiple_question(
        event_info: Dict[str, str],
        max_retries: int = DEFAULT_RETRY_COUNT, 
        delay: int = DEFAULT_RETRY_DELAY
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]], Optional[str], Optional[str]]:
        """
        Generate a multiple-option betting question for tournaments or leagues.
        
        Args:
            event_info: Dictionary containing event information
            max_retries: Maximum number of retries
            delay: Delay between retries in seconds
            
        Returns:
            Tuple of (question, options_array, end_date, event_description)
        """
        current_date = datetime.now().date()
        prompt_template = """
        You are a sports analyst and betting market creator. Given the following event details, generate:

        - A clear betting question about the future event.
        - A list of outcome options that:
            * Includes ALL specific teams/participants mentioned in the description
            * For tournaments/leagues, includes ALL major confirmed participating teams 
            * For matches between specific teams, includes ALL teams mentioned
        - Provide realistic probabilities for each option that sum to exactly 100%
        - Use only clean team/participant names without any prefixes/formatting
        - Do not include vague options like "Other team" or "Field"
        - Do not include a year or date in the question unless it's a future year (relative to today's date i.e.{current_date})

        Expected Output Format:
        Generated Question: [Clear betting question about future event]
        Probability: Paris Saint-Germain 35, Real Madrid 30, Bayern Munich 20, Manchester City 15
        Event Description: [2–4 sentence engaging and factual description]

        Event Details:
        Title: {title}
        Topic: {topic}
        Description: {description}

        Important:
        - List ALL teams mentioned in clean format (e.g. "Team Name 25")
        - Each team mentioned must have a probability assigned
        - Total probabilities must sum to exactly 100%
        - Do not add any formatting characters or prefixes to team names
        """

        for attempt in range(max_retries):
            try:
                prompt = PromptTemplate(template=prompt_template)
                message = prompt.format(
                    title=event_info['Title'],
                    topic=event_info['Topic'],
                    description=event_info['Description'],
                    current_date=current_date
                )

                response = await openai_model.ainvoke(message)
                data = response.content
                
                if 'Generated Question:' in data:
                    # Extract the question
                    start_index = data.find('Generated Question:') + len('Generated Question:')
                    end_index = data.find('Probability:') if 'Probability:' in data else len(data)
                    generated_question = data[start_index:end_index].strip()

                    match_question = re.search(r'.*?\?', generated_question)
                    if match_question:
                        generated_question = match_question.group(0)

                    # Extract the event description
                    if 'Event Description:' in data:
                        desc_start_index = data.find('Event Description:') + len('Event Description:')
                        event_description = data[desc_start_index:].strip()
                    else:
                        event_description = None
                        logger.warning("Event Description not found in response")

                    # Extract and validate multi-option probabilities
                    prob_index = data.find('Probability:')
                    event_desc_index = data.find('Event Description:')
                    probability_section = data[prob_index + len('Probability:'):event_desc_index].strip() if event_desc_index > 0 else data[prob_index + len('Probability:'):].strip()

                    option_matches = re.findall(r"([\w''\-&]+(?:\s[\w''\-&]+)*):\s*(\d+)", probability_section)
                    option_array = [{"option": option.strip(), "probability": int(prob.strip())} for option, prob in option_matches]

                    if option_array:
                        total_prob = sum(opt['probability'] for opt in option_array)
                        valid_options = all(0 <= opt['probability'] <= 100 for opt in option_array)
                        no_field_option = all(opt['option'].lower() not in ['field', 'any other team', 'others', 'other team'] for opt in option_array)

                        if total_prob == 100 and valid_options and no_field_option:
                            return generated_question, option_array, None, event_description
                        else:
                            logger.info("Invalid or vague options or total probability != 100.")
                    else:
                        logger.info("No valid probabilities found in response.")
                else:
                    logger.info("Missing required keys in response.")
                    
            except Exception as e:
                logger.exception(f"Error generating multiple question (attempt {attempt+1}): {e}")
                
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
    
        return None, None, None, None


# Function aliases for backward compatibility
async def generate_question_from_API(*args, **kwargs):
    """Backward compatibility function for generate_question_from_API."""
    return await SportsApiService.generate_question_from_api(*args, **kwargs)

async def generate_multiple_question(*args, **kwargs):
    """Backward compatibility function for generate_multiple_question."""
    return await SportsApiService.generate_multiple_question(*args, **kwargs)

def fetch_sports_data(*args, **kwargs):
    """Backward compatibility function for fetch_sports_data."""
    service = SportsApiService()
    return service.fetch_sports_data(*args, **kwargs)

def organize_sports_events(*args, **kwargs):
    """Backward compatibility function for organize_sports_events."""
    service = SportsApiService()
    return service.organize_sports_events(*args, **kwargs)