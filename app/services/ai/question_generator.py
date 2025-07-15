"""
Question Generator Service.

This module provides functionality to generate betting questions
and related content using AI models.
"""
import re
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from app.config.settings import OPENAI_API_KEY, DEFAULT_MODEL, DEFAULT_RETRY_COUNT, DEFAULT_RETRY_DELAY

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI model
openai_model = ChatOpenAI(api_key=OPENAI_API_KEY, model=DEFAULT_MODEL)

class QuestionGeneratorService:
    """Service for generating betting questions and related content."""
    
    @staticmethod
    async def generate_question(
        event_description: str,
        category_name: str,
        event_type: str,
        max_retries: int = DEFAULT_RETRY_COUNT,
        delay: int = DEFAULT_RETRY_DELAY
    ) -> Tuple[Optional[str], Optional[Union[int, List[Dict[str, Any]]]], Optional[int], Optional[str]]:
        """
        Generate a betting question based on event description.
        
        Returns:
            Tuple of (question, probability_yes|options, probability_no, end_date)
        """
        current_date = datetime.now().date()
        current_date_str = current_date.strftime('%Y-%m-%d')
        # Calculate date 4 months later, handling year change if needed
        four_months_later = current_date.replace(month=current_date.month + 4) if current_date.month <= 8 else current_date.replace(year=current_date.year + 1, month=(current_date.month + 4) % 12)
        
        prompt_template = """
        You are a betting application bot responsible for creating precise betting questions about FUTURE events. Follow these strict guidelines:

        CORE REQUIREMENTS:
        1. Question MUST ONLY be about events occurring STRICTLY AFTER {current_date_str} and BEFORE {four_months_later}.
        2. The event date and resolution date MUST NOT be {current_date_str}.
        3. Question MUST relate directly to {event_type} and {category_name}.
        4. Format requirements:
           FIRST: Analyze if multiple MEANINGFUL and SPECIFIC options exist in the event description
           - If multiple NAMED options exist: Create a multi-option question with actual names/entities
           - If no clear named options exist: Default to binary clear yes/no or either/or questions
           - AVOID generic placeholders like "Team A", "Others", "Unknown"
        5. Maximum 25 words, using actual names/entities only
        6. Must be future-focused and verifiable

        PROBABILITY ASSIGNMENT PRIORITY:
        1. Multi-option format (only with specific named entities):
           - Use actual names/entities from the description
           - Each option must be a real, identifiable entity
           - Assign realistic probabilities to each named option
           - Total must equal 100%
        2. Binary format (when specific options aren't available):
           - Yes: X%, No: Y% (must total 100%)
           - Use when multiple named options aren't feasible

        MARKET RESOLUTION DATE:
        1. Must be AFTER {current_date_str} but BEFORE {four_months_later}
        2. Use actual event date if provided
        3. Must be specific and verifiable
        4. Cannot match current date

        VALIDATION CHECKS:
        - Confirms event is in future ✓
        - Verifies dates are valid ✓
        - Ensures objective measurement ✓
        - Checks for specific named entities ✓
        - Validates multiple options are real entities ✓

        Inputs:
        - Event Description: {event_description}
        - Category Name: {category_name}
        - Event Type: {event_type}
        - Current Date: {current_date_str}

        Expected Output Format:
        Generated Question: [Future-focused betting question]
        Probability: [Named multi-option probabilities or binary]
        Market Resolution Date: [Future date with reasoning]

        Return None if:
        - Event isn't clearly in future
        - Dates invalid or match current date
        - Missing specific entities
        - Unclear resolution criteria
        - Only generic options available
        """
        
        for attempt in range(max_retries):
            try:
                # Format the prompt using the template
                prompt = PromptTemplate(template=prompt_template)
                message = prompt.format(
                    event_description=event_description,
                    category_name=category_name,
                    event_type=event_type,
                    current_date_str=current_date_str,
                    four_months_later=four_months_later
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
                
                if 'Generated Question:' in data and 'Market Resolution Date:' in data:
                    # Extract the question from the response
                    start_index = data.find('Generated Question:') + len('Generated Question:')
                    end_index = data.find('Probability:') if 'Probability:' in data else len(data)
                    generated_question = data[start_index:end_index].strip()

                    # Ensure we capture the full question ending with a question mark
                    match_question = re.search(r'.*\?', generated_question)
                    if match_question:
                        generated_question = match_question.group(0)

                    # Extract the end date from the response
                    end_date = data[data.find('Market Resolution Date:')+len("Market Resolution Date:"):len(data)].strip()
                    
                    # Extract the probability section from the response
                    prob_index = data.find('Probability:')
                    if prob_index != -1:
                        market_date_index = data.find('Market Resolution Date:')
                        probability_section = data[prob_index + len('Probability:'):market_date_index].strip()
                        
                        # Check for binary Yes/No format
                        binary_yes = re.search(r'Yes\s*:\s*(\d+)', probability_section)
                        binary_no = re.search(r'No\s*:\s*(\d+)', probability_section)

                        if binary_yes and binary_no:
                            yes_probability = int(binary_yes.group(1))
                            no_probability = int(binary_no.group(1))
                            if yes_probability + no_probability == 100 and 0 <= yes_probability <= 100:
                                return generated_question, int(yes_probability), int(no_probability), end_date
                        else:
                            # Check for multi-option format
                            option_matches = re.findall(r"([\w']+(?:\s[\w']+)*):\s*(\d+)", probability_section)
                            if option_matches:
                                option_array = [{"option": option.strip(), "probability": int(prob.strip())} for option, prob in option_matches]
                                total_prob = sum(opt['probability'] for opt in option_array)
                                if total_prob == 100 and all(0 <= opt['probability'] <= 100 for opt in option_array):
                                    return generated_question, option_array, None, end_date
                            else:
                                logger.info("No valid probabilities found in response.")
                    else:
                        logger.info("No probability section found in response.")
                    return None, None, None, None
                else:
                    logger.info("Failed to generate betting question for description.")
            except Exception as e:
                logger.exception("Error parsing response. Skipping attempt.")

            logger.info(f"Retrying... ({attempt + 1}/{max_retries})")
            await asyncio.sleep(delay)

        return None, None, None, None  # If max retries are exceeded, return None

    @staticmethod
    async def generate_search_sentence(category: str, topic: str) -> str:
        """
        Generate a search query combining category and topic for relevant results.
        
        Returns:
            Optimized search query string
        """
        # Construct the prompt to instruct OpenAI to generate a meaningful search query
        prompt = PromptTemplate(template=f"""
            I need a concise search query that will return current events or news about a specific topic within a category.
            
            Category: {category}
            Topic: {topic}
            
            The search query should:
            - Include both the category and topic to ensure relevance
            - Be concise and direct (3-6 words)
            - Be ready for direct input into a search engine
            - Focus on recent news/events
            - Not include dates, quotation marks, or special operators
            
            Examples:
            * Category: Sports, Topic: Cricket → "cricket sports news updates"
            * Category: Technology, Topic: Artificial Intelligence → "AI technology latest developments"
            * Category: Finance, Topic: Stock Market → "stock market finance news"
            * Category: Anime, Topic: Adventure → "adventure anime new releases"
            
            Generate the search query:
        """)
        
        # Call OpenAI to generate the response
        response = openai_model.invoke(prompt.format(category=category, topic=topic))
        
        # Extract and clean the generated search query
        search_query = response.content.strip()
        
        # Remove any quotation marks and extra whitespace
        search_query = search_query.replace('"', '').strip()
        
        # If the model didn't include the category, make sure it's present
        if category.lower() not in search_query.lower():
            search_query = f"{topic} {category} {search_query.split(' ')[-1] if len(search_query.split(' ')) > 1 else 'news'}"
        
        return search_query

    @staticmethod
    async def generate_rules(
        generated_question: str, 
        probability: Union[str, List[Dict]], 
        end_date: str,
        max_retries: int = DEFAULT_RETRY_COUNT, 
        delay: int = DEFAULT_RETRY_DELAY
    ) -> Optional[str]:
        """
        Create clear market resolution rules based on the question and probabilities.
        
        Returns:
            Rules as a single paragraph text
        """
        current_date = datetime.now().date()
        current_date_str = current_date.strftime('%Y-%m-%d')

        prompt_template = """
            Create clear and fair market resolution rules in a single paragraph based on the provided probability and end date, ensuring unambiguous resolution for bettors.
            The rules should capture the key resolution criteria while remaining meaningful and coherent.
            
            Inputs:
            - Question: {generated_question}
            - Probability: {probability}
            - Market Resolution Date: {end_date}
            - Current Date: {current_date_str}
            
            Output: 
            - Rules: [Provide a concise, clean-text paragraph detailing resolution criteria, timeframe from {current_date_str} to {end_date}, tie conditions, authoritative sources, and edge cases.]
        """

        for attempt in range(max_retries):
            try:
                prompt = PromptTemplate(template=prompt_template)
                message = prompt.format(
                    generated_question=generated_question,
                    probability=probability,
                    end_date=end_date,
                    current_date_str=current_date_str
                )
                response = openai_model.invoke(message)
                text = (response.content or "").strip()

                # Remove any bold or plain occurrences of 'rules' or 'Rules'
                text = re.sub(r'\*{2}\s*rules?\s*\*{2}', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\b[rR]ules?\b\s*:?\s*', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\*{2}', '', text).strip()

                cleaned = text.strip()
                if cleaned:
                    return cleaned

                # If cleaning strips everything, return None to trigger retry or final fallback
                return None

            except Exception as e:
                logger.exception(f"Error generating rules (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)

        return None

    @staticmethod
    async def summary(event_description: str, generated_question: str) -> str:
        """
        Create a concise summary of the event description related to the question.
        
        Returns:
            Summary text under 100 words
        """
        # Limit event description to 8000 bytes to prevent token overflow
        event_description = event_description[:8000]
        
        # Construct the prompt to instruct OpenAI to generate a very concise summary.
        prompt_template = """
            Create a very concise summary of the following event description, ensuring that the summary is extremely related to the generated question provided.
            The summary should capture the key points while remaining meaningful, coherent, and directly tied to the context of the generated question.
            It must be under 100 words maximum.
            
            Inputs:
            - Event Description: {event_description}
            - Generated Question: {generated_question}

            Output:
            - Summary: [A clear, concise summary under 100 words that relates directly to the generated question.]
        """
        prompt = PromptTemplate(template=prompt_template)
        message = prompt.format(event_description=event_description, generated_question=generated_question)
        
        response = openai_model.invoke(message)
        summary_text = response.content.strip()
        
        # Check if the response contains "Summary:" and remove it if present.
        if "Summary:" in summary_text:
            summary_text = summary_text.replace("Summary:", "").strip()

        # Return the summary if it is not null; otherwise, return the original response.
        if summary_text:
            return summary_text
        return response.content.strip()

    @staticmethod
    async def generate_followup_question(
        previous_question: str, 
        option: str, 
        event_description: str, 
        max_retries: int = DEFAULT_RETRY_COUNT, 
        delay: int = DEFAULT_RETRY_DELAY
    ) -> Optional[str]:
        """
        Generate a follow-up question incorporating a specific option.
        
        Returns:
            Follow-up question text
        """
        if not previous_question or not option:
            logger.error("Missing required parameters")
            return None

        prompt_template = """
        Generated Question: [Clear betting question about future event matching the event_type]
        You are responsible for generating futuristic follow-up questions based on the parent question "{previous_question}".
        The follow-up question must incorporate the options: {option} and be tightly related to the event description "{event_description}".
        Ensure that the question is in proper format, extremely relevant, and contains no more than 25 words.
        The question must be a question and not a statement in future tense.
        """
        
        for attempt in range(max_retries):
            try:
                prompt = PromptTemplate(template=prompt_template)
                message = prompt.format(previous_question=previous_question, option=option, event_description=event_description)
                response = openai_model.invoke(message)
                
                if not response or not response.content:
                    raise ValueError("Empty response from model")
                    
                followup_question = response.content.strip()
                
                # Validate response format
                if not followup_question.endswith('?'):
                    followup_question += '?'
                    
                return followup_question

            except Exception as e:
                logger.error(f"Error generating follow-up question (attempt {attempt+1}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    continue
        return None

# Alias functions for backward compatibility
async def generate_question(*args, **kwargs):
    """Backward compatibility function for generate_question."""
    return await QuestionGeneratorService.generate_question(*args, **kwargs)

async def generate_search_sentence(*args, **kwargs):
    """Backward compatibility function for generate_search_sentence."""
    return await QuestionGeneratorService.generate_search_sentence(*args, **kwargs)

async def summary(*args, **kwargs):
    """Backward compatibility function for summary."""
    return await QuestionGeneratorService.summary(*args, **kwargs)

async def generate_rules(*args, **kwargs):
    """Backward compatibility function for generate_rules."""
    return await QuestionGeneratorService.generate_rules(*args, **kwargs)

async def generate_followup_question(*args, **kwargs):
    """Backward compatibility function for generate_followup_question."""
    return await QuestionGeneratorService.generate_followup_question(*args, **kwargs)