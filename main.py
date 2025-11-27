"""
Prediction Market App - Main Application

This script orchestrates the automated generation of prediction market events
by collecting and processing data from various sources.
"""
import os
import asyncio
import logging
import random
from datetime import datetime

import requests  # for catching HTTPError from google_image_search
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import our custom MongoDB logging setup
from app.utils.mongodb_logging import (
    setup_mongodb_logging,
    LoggedFunction,
    log_database_operation,
    cleanup_all_logs,
)

# Setup MongoDB logging (this will replace the basic logging config)
mongo_handler = setup_mongodb_logging(
    level=logging.INFO,
    collection_name="prediction_market_logs",
    console_logging=True,  # Set to False for production if you don't want console output
    use_async_handler=True,
)

# Get logger for this module
logger = logging.getLogger(__name__)

from app.models.event import EventData, OptionData, save_event
from app.config.db import get_event_collection, get_collection
from app.services.search.google_search import google_search, google_image_search
from app.services.scrapers.web_scraper import document_loader
from app.services.sports.sports_api import (
    SportsApiService,
    organize_sports_events,
    fetch_sports_data,
    generate_question_from_API,
    generate_multiple_question,
)
from app.services.ai.question_generator import (
    generate_question,
    generate_search_sentence,
    summary,
    generate_rules,
    generate_followup_question,
)
from app.services.ai.sentiment_analyzer import analyze_document
from app.services.storage.s3_service import upload_image_to_s3
from app.utils.helper_functions import get_categories_with_topics
from app.utils.date_utils import parse_date

from bson.objectid import ObjectId


# -------------------------------------------------
# Google Image Search – quota-aware safe wrapper
# -------------------------------------------------
IMAGE_SEARCH_DISABLED = False
IMAGE_SEARCH_COUNT = 0
MAX_IMAGE_SEARCHES_PER_RUN = int(os.getenv("MAX_IMAGE_SEARCHES_PER_RUN", "200"))


def safe_google_image_search(query: str):
    """
    Wrapper around google_image_search that:
    - Stops completely after first 429 (daily quota hit)
    - Caps total image searches per run
    - Returns None instead of raising, so caller can skip upload
    """
    global IMAGE_SEARCH_DISABLED, IMAGE_SEARCH_COUNT

    if IMAGE_SEARCH_DISABLED:
        logger.debug("Image search disabled for this run; skipping call.")
        return None

    if IMAGE_SEARCH_COUNT >= MAX_IMAGE_SEARCHES_PER_RUN:
        logger.warning(
            f"Skipping image search for '{query}': "
            f"per-run cap {MAX_IMAGE_SEARCHES_PER_RUN} reached."
        )
        return None

    try:
        IMAGE_SEARCH_COUNT += 1
        return google_image_search(query)

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status == 429:
            logger.error(
                "Received 429 from Google Custom Search. "
                "Disabling further image searches for this run."
            )
            IMAGE_SEARCH_DISABLED = True
            return None

        logger.error(f"HTTP error in google_image_search('{query}'): {e}", exc_info=True)
        return None

    except Exception as e:
        # Catch-all to avoid breaking event generation on image failures
        logger.error(f"Unexpected error in google_image_search('{query}'): {e}", exc_info=True)
        return None


async def process_sport_events(category_name, category_id):
    """
    Process sports events from API and save to database.

    Args:
        category_name: Name of the sports category
        category_id: ObjectId of the category
    """
    with LoggedFunction("process_sport_events", logger, category=category_name):
        logger.info(f"Processing sports events for category: {category_name}")

        try:
            # Initialize sports service and fetch data
            sports_service = SportsApiService()
            results = sports_service.fetch_sports_data()
            organized_events, null_team_events = sports_service.organize_sports_events(results)

            logger.info(
                f"Retrieved {len(organized_events)} team events and {len(null_team_events)} null team events"
            )

            # Process events with teams
            team_events_processed = 0
            for event in organized_events:
                try:
                    event_info = {
                        "Topic": event["topic"],
                        "Description": event["description"],
                        "Event": event["event_description"],
                        "End Date": event["formatted_date"],
                    }

                    (
                        generated_question,
                        prob1,
                        prob2,
                        end_date,
                        event_description,
                    ) = await generate_question_from_API(event_info)
                    if not (generated_question and end_date):
                        logger.warning(
                            f"Skipping sport event: No valid question generated for topic {event['topic']}"
                        )
                        continue

                    # Binary question format
                    if prob2 is not None:
                        rules = await generate_rules(
                            generated_question, f"Yes: {prob1}%, No: {prob2}%", end_date
                        )

                        event_image_url = None
                        image_url = safe_google_image_search(generated_question)
                        if image_url:
                            try:
                                event_image_url = await upload_image_to_s3(
                                    image_url, str(int(datetime.now().timestamp() * 1000))
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error uploading sports event image: {e}", exc_info=True
                                )

                        event_data = EventData(
                            is_approved=False,
                            is_child=False,
                            is_sport_page=True,
                            sport_key=event["key"],
                            category=category_id,
                            topic=None,
                            has_options=False,
                            title=generated_question,
                            end_date=end_date,
                            event_description=event_description,
                            rules=rules,
                            probability_of_yes=prob1,
                            probability_of_no=prob2,
                            options=None,
                            event_image=event_image_url,
                            source_link=None,
                            created_date=datetime.now(),
                        )

                        if await save_event(event_data):
                            team_events_processed += 1
                            log_database_operation("INSERT", "events", 1, logger)
                            logger.info(
                                f"Binary sports event saved successfully: {generated_question}"
                            )
                        else:
                            logger.error(
                                f"Failed to save binary sports event: {generated_question}"
                            )

                except Exception as e:
                    logger.error(
                        f"Error processing team event {event.get('topic', 'unknown')}: {str(e)}",
                        exc_info=True,
                    )
                    continue

            # Process events without teams
            null_events_processed = 0
            for event in null_team_events:
                try:
                    success = await process_null_team_event(event, category_id)
                    if success:
                        null_events_processed += 1
                except Exception as e:
                    logger.error(
                        f"Error processing null team event {event.get('topic', 'unknown')}: {str(e)}",
                        exc_info=True,
                    )
                    continue

            logger.info(
                f"Sports events processing completed. Team events: {team_events_processed}, "
                f"Null team events: {null_events_processed}"
            )

        except Exception as e:
            logger.error(f"Critical error in process_sport_events: {str(e)}", exc_info=True)
            raise


async def process_null_team_event(event, category_id):
    """
    Process and save events without specific teams.

    Args:
        event: Event information dictionary
        category_id: ObjectId of the category

    Returns:
        bool: True if successfully processed, False otherwise
    """
    with LoggedFunction("process_null_team_event", logger, event_key=event.get("key")):
        event_info = {
            "Topic": event["topic"],
            "Title": event["title"],
            "Description": event["description"],
        }

        (
            generated_question,
            prob1,
            prob2,
            event_description,
        ) = await generate_multiple_question(event_info)
        if not (generated_question and event.get("formatted_date")):
            logger.warning(
                f"Skipping null team event: No valid question generated for {event.get('topic')}"
            )
            return False

        rules = await generate_rules(generated_question, prob1, event["formatted_date"])

        parent_event_image_url = None
        image_url = safe_google_image_search(generated_question)
        if image_url:
            try:
                parent_event_image_url = await upload_image_to_s3(
                    image_url, str(int(datetime.now().timestamp() * 1000))
                )
            except Exception as e:
                logger.error(
                    f"Error uploading parent null-team event image: {e}", exc_info=True
                )

        # Create parent event
        event_data = EventData(
            is_approved=False,
            is_child=False,
            is_sport_page=True,
            sport_key=event["key"],
            category=category_id,
            topic=None,
            has_options=True,
            title=generated_question,
            end_date=event["formatted_date"],
            event_description=event_description,
            rules=rules,
            probability_of_yes=None,
            probability_of_no=None,
            options=None,
            event_image=parent_event_image_url,
            source_link=None,
            created_date=datetime.now(),
        )

        # Save parent multi-option event
        save_response = await save_event(event_data)
        if not save_response:
            logger.error("Failed to save the multi-option event.")
            return False

        log_database_operation("INSERT", "events", 1, logger)
        logger.info("Multi-option event saved successfully.")
        parent_event_id = (
            save_response["inserted_id"]
            if isinstance(save_response, dict)
            else save_response
        )

        # Process and save binary events for each option
        updated_options = []
        options_processed = 0

        for option in prob1:
            try:
                option_name = option["option"]
                option_prob = option["probability"]
                prob_yes = option_prob
                prob_no = 100 - prob_yes

                binary_title = await generate_followup_question(
                    generated_question, option_name, event_description
                )

                binary_event_image_url = None
                image_url = safe_google_image_search(option_name)
                if image_url:
                    try:
                        binary_event_image_url = await upload_image_to_s3(
                            image_url, str(int(datetime.now().timestamp() * 1000))
                        )
                    except Exception as e:
                        logger.error(
                            f"Error uploading image for option '{option_name}' "
                            f"in null-team event: {e}",
                            exc_info=True,
                        )

                # Create child event
                binary_event_data = EventData(
                    is_approved=False,
                    is_child=True,
                    is_sport_page=True,
                    sport_key=event["key"],
                    category=category_id,
                    topic=None,
                    has_options=False,
                    title=binary_title,
                    end_date=event["formatted_date"],
                    event_description=event_description,
                    rules=await generate_rules(
                        binary_title,
                        f"Yes: {prob_yes}%, No: {prob_no}%",
                        event["formatted_date"],
                    ),
                    probability_of_yes=prob_yes,
                    probability_of_no=prob_no,
                    options=None,
                    event_image=binary_event_image_url,
                    source_link=None,
                    created_date=datetime.now(),
                )

                binary_save_response = await save_event(binary_event_data)
                if binary_save_response:
                    binary_event_id = (
                        binary_save_response["inserted_id"]
                        if isinstance(binary_save_response, dict)
                        else binary_save_response
                    )
                    binary_event_id = (
                        ObjectId(binary_event_id)
                        if isinstance(binary_event_id, str)
                        else binary_event_id
                    )
                    logger.info(
                        f"Binary event for option '{option_name}' saved with ID: {binary_event_id}"
                    )

                    # Create option with foreign key reference
                    option_data = OptionData(
                        option=option_name,
                        probability=option_prob,
                        market=binary_event_id,
                    )
                    updated_options.append(option_data)
                    options_processed += 1
                else:
                    logger.error(
                        f"Failed to save binary event for option '{option_name}'"
                    )

            except Exception as e:
                logger.error(
                    f"Error processing option '{option.get('option', 'unknown')}': {str(e)}",
                    exc_info=True,
                )
                continue

        # Update parent event with option references
        if updated_options:
            try:
                db_collection = await get_event_collection()
                parent_id = (
                    ObjectId(parent_event_id)
                    if isinstance(parent_event_id, str)
                    else parent_event_id
                )
                update_result = await db_collection.update_one(
                    {"_id": parent_id},
                    {"$set": {"options": [opt.dict() for opt in updated_options]}},
                )
                if update_result.modified_count > 0:
                    log_database_operation("UPDATE", "events", 1, logger)
                    logger.info(
                        f"Parent event '{parent_event_id}' updated with "
                        f"{len(updated_options)} options successfully."
                    )
                else:
                    logger.error(
                        f"Failed to update parent event '{parent_event_id}' with options."
                    )
                    return False
            except Exception as e:
                logger.error(
                    f"Error updating parent event with options: {str(e)}", exc_info=True
                )
                return False

        logger.info(
            f"Null team event processed successfully. Options created: {options_processed}"
        )
        return True


async def process_regular_event(event):
    """
    Process and save standard (non-sports) events.

    Args:
        event: Event information dictionary
    """
    row = event["row"]

    with LoggedFunction(
        "process_regular_event",
        logger,
        url=row["Link"],
        category=event["category_name"],
        topic=event["topic_name"],
    ):
        logger.info(
            f"Processing URL: {row['Link']} "
            f"(Category: {event['category_name']}, Topic: {event['topic_name']})"
        )

        try:
            # Get event content
            event_description = await document_loader(row["Link"])
            if event_description is None:
                logger.warning(
                    f"No content retrieved for URL: {row['Link']}. Skipping."
                )
                return False

            # Generate question based on content
            result = await generate_question(
                event_description, event["category_name"], event["topic_name"]
            )
            if not result:
                logger.warning("No valid question generated. Skipping.")
                return False

            generated_question, prob1, prob2, end_date = result
            event_description = await summary(event_description, generated_question)

            if not (generated_question and end_date):
                logger.warning("Missing question or end date. Skipping.")
                return False

            # Handle binary question format
            if prob2 is not None:
                success = await save_binary_event(
                    event,
                    generated_question,
                    prob1,
                    prob2,
                    end_date,
                    event_description,
                    row,
                )
            # Handle multi-option question format
            else:
                success = await save_multi_option_event(
                    event,
                    generated_question,
                    prob1,
                    end_date,
                    event_description,
                    row,
                )

            return success

        except Exception as e:
            logger.error(
                f"Error processing event for URL {row['Link']}: {str(e)}",
                exc_info=True,
            )
            return False


async def save_binary_event(event, question, prob1, prob2, end_date, description, row):
    """
    Save a binary yes/no event.
    """
    with LoggedFunction("save_binary_event", logger, question=question):
        try:
            rules = await generate_rules(
                question, f"Yes: {prob1}%, No: {prob2}%", end_date
            )

            event_image_url = None
            image_url = safe_google_image_search(question)
            if image_url:
                try:
                    event_image_url = await upload_image_to_s3(
                        image_url, str(int(datetime.now().timestamp() * 1000))
                    )
                except Exception as e:
                    logger.error(
                        f"Error uploading image for binary event '{question}': {e}",
                        exc_info=True,
                    )

            event_data = EventData(
                is_approved=False,
                is_child=False,
                is_sport_page=False,
                sport_key=None,
                category=event["category_id"],
                topic=event["topic_id"],
                has_options=False,
                title=question,
                end_date=parse_date(end_date),
                event_description=description,
                rules=rules,
                probability_of_yes=prob1,
                probability_of_no=prob2,
                options=None,
                event_image=event_image_url,
                source_link=row["Link"],
                created_date=datetime.now(),
            )

            if await save_event(event_data):
                log_database_operation("INSERT", "events", 1, logger)
                logger.info(f"Binary event saved successfully: {question}")
                return True
            else:
                logger.error(f"Failed to save binary event: {question}")
                return False

        except Exception as e:
            logger.error(
                f"Error saving binary event '{question}': {str(e)}", exc_info=True
            )
            return False


async def save_multi_option_event(event, question, options, end_date, description, row):
    """
    Save a multi-option event with child binary events.
    """
    with LoggedFunction(
        "save_multi_option_event", logger, question=question, options_count=len(options)
    ):
        try:
            rules = await generate_rules(question, options, end_date)

            parent_event_image_url = None
            image_url = safe_google_image_search(question)
            if image_url:
                try:
                    parent_event_image_url = await upload_image_to_s3(
                        image_url, str(int(datetime.now().timestamp() * 1000))
                    )
                except Exception as e:
                    logger.error(
                        f"Error uploading parent image for multi-option event "
                        f"'{question}': {e}",
                        exc_info=True,
                    )

            # Create parent event
            event_data = EventData(
                is_approved=False,
                is_child=False,
                is_sport_page=False,
                sport_key=None,
                category=event["category_id"],
                topic=event["topic_id"],
                has_options=True,
                title=question,
                end_date=parse_date(end_date),
                event_description=description,
                rules=rules,
                probability_of_yes=None,
                probability_of_no=None,
                options=None,
                event_image=parent_event_image_url,
                source_link=row["Link"],
                created_date=datetime.now(),
            )

            # Save parent multi-option event
            save_response = await save_event(event_data)
            if not save_response:
                logger.error("Failed to save the multi-option event.")
                return False

            log_database_operation("INSERT", "events", 1, logger)
            parent_event_id = (
                save_response["inserted_id"]
                if isinstance(save_response, dict)
                else save_response
            )
            updated_options = []
            options_processed = 0

            # Create and save binary events for each option
            for option in options:
                try:
                    option_name = option["option"]
                    option_prob = option["probability"]
                    prob_yes = option_prob
                    prob_no = 100 - prob_yes

                    # Generate follow-up question for this option
                    binary_title = await generate_followup_question(
                        question, option_name, description
                    )

                    binary_event_image_url = None
                    image_url = safe_google_image_search(option_name)
                    if image_url:
                        try:
                            binary_event_image_url = await upload_image_to_s3(
                                image_url,
                                str(int(datetime.now().timestamp() * 1000)),
                            )
                        except Exception as e:
                            logger.error(
                                f"Error uploading image for option '{option_name}' "
                                f"in multi-option event: {e}",
                                exc_info=True,
                            )

                    # Create child event for this option
                    binary_event_data = EventData(
                        is_approved=False,
                        is_child=True,
                        is_sport_page=False,
                        sport_key=None,
                        category=event["category_id"],
                        topic=event["topic_id"],
                        has_options=False,
                        title=binary_title,
                        end_date=parse_date(end_date),
                        event_description=description,
                        rules=await generate_rules(
                            binary_title,
                            f"Yes: {prob_yes}%, No: {prob_no}%",
                            end_date,
                        ),
                        probability_of_yes=prob_yes,
                        probability_of_no=prob_no,
                        options=None,
                        event_image=binary_event_image_url,
                        source_link=row["Link"],
                        created_date=datetime.now(),
                    )

                    # Save this child event
                    binary_save_response = await save_event(binary_event_data)
                    if binary_save_response:
                        binary_event_id = (
                            binary_save_response["inserted_id"]
                            if isinstance(binary_save_response, dict)
                            else binary_save_response
                        )
                        binary_event_id = (
                            ObjectId(binary_event_id)
                            if isinstance(binary_event_id, str)
                            else binary_event_id
                        )

                        # Create option reference
                        option_data = OptionData(
                            option=option_name,
                            probability=option_prob,
                            market=binary_event_id,
                        )
                        updated_options.append(option_data)
                        options_processed += 1
                        logger.info(
                            f"Created binary event for option '{option_name}' "
                            f"with ID: {binary_event_id}"
                        )
                    else:
                        logger.error(
                            f"Failed to save binary event for option '{option_name}'"
                        )

                except Exception as e:
                    logger.error(
                        f"Error processing option '{option.get('option', 'unknown')}': {str(e)}",
                        exc_info=True,
                    )
                    continue

            # Update parent event with option references
            if updated_options:
                try:
                    db_collection = await get_event_collection()
                    parent_id = (
                        ObjectId(parent_event_id)
                        if isinstance(parent_event_id, str)
                        else parent_event_id
                    )
                    update_result = await db_collection.update_one(
                        {"_id": parent_id},
                        {"$set": {"options": [opt.dict() for opt in updated_options]}},
                    )
                    if update_result.modified_count > 0:
                        log_database_operation("UPDATE", "events", 1, logger)
                        logger.info(
                            f"Parent event '{parent_event_id}' updated with "
                            f"{len(updated_options)} options successfully."
                        )
                    else:
                        logger.error(
                            f"Failed to update parent event '{parent_event_id}' with options."
                        )
                        return False
                except Exception as e:
                    logger.error(
                        f"Error updating parent event with options: {str(e)}",
                        exc_info=True,
                    )
                    return False

            logger.info(
                f"Multi-option event processed successfully. Options created: {options_processed}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error saving multi-option event '{question}': {str(e)}",
                exc_info=True,
            )
            return False


async def main():
    """Main function to collect and process events."""
    with LoggedFunction("main", logger):
        logger.info("Starting prediction market data extraction and processing")

        try:
            # Clean up ALL previous logs for fresh start
            logger.info("Cleaning up all previous logs for fresh start...")
            deleted_count = await cleanup_all_logs(
                "prediction_market_logs", logger=logger
            )
            logger.info(f"Log cleanup completed. Deleted {deleted_count} log entries.")

        except Exception as e:
            logger.warning(
                f"Log cleanup failed: {str(e)}. Continuing with main process..."
            )

        try:
            # Collection Phase: Build a list of events
            subreddits = await get_categories_with_topics()
            all_events = []

            # For testing, limit to just this category
            # subreddits = {'Politics_67af0d491551b6b63d6e1d9f': ['Iran_67ce927276857b52f0869351']}
            logger.info(f"Processing {len(subreddits)} categories")

            for category, topics in subreddits.items():
                try:
                    category_name, category_id_str = category.rsplit("_", 1)
                    category_id = ObjectId(category_id_str)

                    # Process sports events separately
                    if category_name.lower() == "sports":
                        await process_sport_events(category_name, category_id)
                        continue

                    # Process regular events
                    if not topics:
                        logger.warning(
                            f"No topics found for category '{category_name}'. Skipping."
                        )
                        continue

                    logger.info(
                        f"Collecting events for category: {category_name} "
                        f"with {len(topics)} topics"
                    )

                    for topic in topics:
                        try:
                            topic_name, topic_id_str = topic.rsplit("_", 1)
                            topic_id = ObjectId(topic_id_str)

                            # Generate search query and fetch URLs
                            subreddit = await generate_search_sentence(
                                category_name, topic_name
                            )
                            logger.info(
                                f"Searching events for topic '{topic_name}' using: {subreddit}"
                            )
                            dataFrame = await google_search(subreddit)

                            # Add each event to our collection list
                            for index, row in dataFrame.iterrows():
                                all_events.append(
                                    {
                                        "category_name": category_name,
                                        "category_id": category_id,
                                        "topic_name": topic_name,
                                        "topic_id": topic_id,
                                        "row": row,
                                        "subreddit": subreddit,
                                    }
                                )

                            logger.info(
                                f"Found {len(dataFrame)} events for topic '{topic_name}'"
                            )
                            await asyncio.sleep(5)  # Pause between topics

                        except Exception as e:
                            logger.error(
                                f"Error processing topic '{topic}' in category "
                                f"'{category_name}': {str(e)}",
                                exc_info=True,
                            )
                            continue

                except Exception as e:
                    logger.error(
                        f"Error processing category '{category}': {str(e)}",
                        exc_info=True,
                    )
                    continue

            logger.info(f"Total collected events: {len(all_events)}")

            # Process events in random order to avoid bias
            random.shuffle(all_events)
            successful_events = 0
            failed_events = 0

            for i, event in enumerate(all_events, 1):
                try:
                    logger.info(f"Processing event {i}/{len(all_events)}")
                    success = await process_regular_event(event)
                    if success:
                        successful_events += 1
                    else:
                        failed_events += 1
                    await asyncio.sleep(2)  # Short pause between processing
                except Exception as e:
                    failed_events += 1
                    logger.error(
                        f"Failed to process event {i}: {str(e)}", exc_info=True
                    )
                    continue

            logger.info(
                f"Data extraction and processing completed. "
                f"Successful: {successful_events}, Failed: {failed_events}"
            )

        except Exception as e:
            logger.error(f"Critical error in main function: {str(e)}", exc_info=True)
            raise
        finally:
            # Ensure all logs are flushed to database
            if hasattr(mongo_handler, "close_async"):
                await mongo_handler.close_async()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
    except Exception as e:
        logger.critical(
            f"Script failed with critical error: {str(e)}", exc_info=True
        )
    finally:
        logger.info("Script execution finished")
