# """
# Prediction Market App - Main Application

# This script orchestrates the automated generation of prediction market events
# by collecting and processing data from various sources.
# """
# import os
# import asyncio
# import logging
# import random
# from datetime import datetime
# from dotenv import load_dotenv

# # Configure logging
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# # Reduce logging noise from HTTP libraries
# for logger_name in ["aiohttp", "urllib3"]:
#     logging.getLogger(logger_name).setLevel(logging.WARNING)

# # Load environment variables
# load_dotenv()

# from app.models.event import EventData, OptionData, save_event
# from app.config.db import get_event_collection
# from app.services.search.google_search import google_search, google_image_search
# from app.services.scrapers.web_scraper import document_loader
# from app.services.sports.sports_api import (
#     SportsApiService, 
#     organize_sports_events, 
#     fetch_sports_data, 
#     generate_question_from_API, 
#     generate_multiple_question
# )
# from app.services.ai.question_generator import (
#     generate_question,
#     generate_search_sentence,
#     summary,
#     generate_rules,
#     generate_followup_question
# )
# from app.services.ai.sentiment_analyzer import analyze_document
# from app.services.storage.s3_service import upload_image_to_s3
# from app.utils.helper_functions import get_categories_with_topics
# from app.utils.date_utils import parse_date

# from bson.objectid import ObjectId

# async def process_sport_events(category_name, category_id):
#     """
#     Process sports events from API and save to database.
    
#     Args:
#         category_name: Name of the sports category
#         category_id: ObjectId of the category
#     """
#     logging.info("Processing sports events")
    
#     # Initialize sports service and fetch data
#     sports_service = SportsApiService()
#     results = sports_service.fetch_sports_data()
#     organized_events, null_team_events = sports_service.organize_sports_events(results)
    
#     # Process events with teams
#     for event in organized_events: # [-5:]  # Process last 5 events for testing
#         event_info = {
#             'Topic': event['topic'],
#             'Description': event['description'],
#             'Event': event['event_description'],
#             'End Date': event['formatted_date']
#         }
        
#         generated_question, prob1, prob2, end_date, event_description = await generate_question_from_API(event_info)
#         if not (generated_question and end_date):
#             logging.info(f"Skipping sport event: No valid question generated")
#             continue
            
#         # Binary question format
#         if prob2 is not None:
#             rules = await generate_rules(generated_question, f"Yes: {prob1}%, No: {prob2}%", end_date)
#             image_url = google_image_search(generated_question)
#             url = await upload_image_to_s3(image_url, str(int(datetime.now().timestamp() * 1000)))
#             event_data = EventData(
#                 is_approved=False,
#                 is_child=False,
#                 is_sport_page=True,
#                 sport_key=event['key'],
#                 category=category_id,
#                 topic=None,
#                 has_options=False,
#                 title=generated_question,
#                 end_date=end_date,
#                 event_description=event_description,
#                 rules=rules,
#                 probability_of_yes=prob1,
#                 probability_of_no=prob2,
#                 options=None,
#                 event_image=url,
#                 source_link=None,
#                 created_date=datetime.now()
#             )
#             if await save_event(event_data):
#                 logging.info("Binary sports event saved successfully.")
    
#     # Process events without teams
#     for event in null_team_events: # [-5:]  # Process last 5 events for testing
#         await process_null_team_event(event, category_id)

# async def process_null_team_event(event, category_id):
#     """
#     Process and save events without specific teams.
    
#     Args:
#         event: Event information dictionary
#         category_id: ObjectId of the category
#     """
#     event_info = {
#         'Topic': event['topic'],
#         'Title': event['title'],
#         'Description': event['description']
#     }
    
#     generated_question, prob1, prob2, event_description = await generate_multiple_question(event_info)
#     if not (generated_question and event.get('formatted_date')):
#         logging.info(f"Skipping null team event: No valid question generated")
#         return
        
#     rules = await generate_rules(generated_question, prob1, event['formatted_date'])
#     image_url = google_image_search(generated_question)
#     url = await upload_image_to_s3(image_url, str(int(datetime.now().timestamp() * 1000)))
    
#     # Create parent event
#     event_data = EventData(
#         is_approved=False,
#         is_child=False,
#         is_sport_page=True,
#         sport_key=event['key'],
#         category=category_id,
#         topic=None,
#         has_options=True,
#         title=generated_question,
#         end_date=event['formatted_date'],
#         event_description=event_description,
#         rules=rules,
#         probability_of_yes=None,
#         probability_of_no=None,
#         options=None,
#         event_image=url,
#         source_link=None,
#         created_date=datetime.now()
#     )
    
#     # Save parent multi-option event
#     save_response = await save_event(event_data)
#     if not save_response:
#         logging.error("Failed to save the multi-option event.")
#         return
        
#     logging.info("Multi-option event saved successfully.")
#     parent_event_id = save_response['inserted_id'] if isinstance(save_response, dict) else save_response
    
#     # Process and save binary events for each option
#     updated_options = []
#     for option in prob1:
#         option_name = option['option']
#         option_prob = option['probability']
#         prob_yes = option_prob
#         prob_no = 100 - prob_yes
        
#         binary_title = await generate_followup_question(generated_question, option_name, event_description)
#         image_url = google_image_search(option_name)
#         url = await upload_image_to_s3(image_url, str(int(datetime.now().timestamp() * 1000)))
        
#         # Create child event
#         binary_event_data = EventData(
#             is_approved=False,
#             is_child=True,
#             is_sport_page=True,
#             sport_key=event['key'],
#             category=category_id,
#             topic=None,
#             has_options=False,
#             title=binary_title,
#             end_date=event['formatted_date'],
#             event_description=event_description,
#             rules=await generate_rules(binary_title, f"Yes: {prob_yes}%, No: {prob_no}%", event['formatted_date']),
#             probability_of_yes=prob_yes,
#             probability_of_no=prob_no,
#             options=None,
#             event_image=url,
#             source_link=None,
#             created_date=datetime.now()
#         )
        
#         binary_save_response = await save_event(binary_event_data)
#         if binary_save_response:
#             binary_event_id = binary_save_response['inserted_id'] if isinstance(binary_save_response, dict) else binary_save_response
#             binary_event_id = ObjectId(binary_event_id) if isinstance(binary_event_id, str) else binary_event_id
#             logging.info(f"Binary event for option '{option_name}' saved with ID: {binary_event_id}")
            
#             # Create option with foreign key reference
#             option_data = OptionData(
#                 option=option_name,
#                 probability=option_prob,
#                 market=binary_event_id
#             )
#             updated_options.append(option_data)
#         else:
#             logging.error(f"Failed to save binary event for option '{option_name}'")
    
#     # Update parent event with option references
#     if updated_options:
#         db_collection = await get_event_collection()
#         parent_id = ObjectId(parent_event_id) if isinstance(parent_event_id, str) else parent_event_id
#         update_result = await db_collection.update_one(
#             {"_id": parent_id},
#             {"$set": {"options": [opt.dict() for opt in updated_options]}}
#         )
#         if update_result.modified_count > 0:
#             logging.info(f"Parent event '{parent_event_id}' updated with options successfully.")
#         else:
#             logging.error(f"Failed to update parent event '{parent_event_id}' with options.")

# async def process_regular_event(event):
#     """
#     Process and save standard (non-sports) events.
    
#     Args:
#         event: Event information dictionary
#     """
#     row = event['row']
#     logging.info(f"Processing URL: {row['Link']} (Category: {event['category_name']}, Topic: {event['topic_name']})")
    
#     try:
#         # Get event content
#         event_description = await document_loader(row['Link'])
#         if event_description is None:
#             logging.info(f"No content retrieved for URL: {row['Link']}. Skipping.")
#             return
            
#         # Generate question based on content
#         # sentiment = await analyze_document(event_description)
#         result = await generate_question(event_description, event['category_name'], event['topic_name'])
#         if not result:
#             logging.info("No valid question generated. Skipping.")
#             return
            
#         generated_question, prob1, prob2, end_date = result
#         event_description = await summary(event_description, generated_question)
        
#         if not (generated_question and end_date):
#             logging.info("Missing question or end date. Skipping.")
#             return
            
#         # Handle binary question format
#         if prob2 is not None:
#             await save_binary_event(
#                 event, generated_question, prob1, prob2, 
#                 end_date, event_description, row
#             )
#         # Handle multi-option question format
#         else:
#             await save_multi_option_event(
#                 event, generated_question, prob1, 
#                 end_date, event_description, row
#             )
            
#     except Exception as e:
#         logging.exception(f"Error processing event for URL {row['Link']}: {e}")

# async def save_binary_event(event, question, prob1, prob2, end_date, description, row):
#     """
#     Save a binary yes/no event.
    
#     Args:
#         event: Event information dictionary
#         question: Generated betting question
#         prob1: Yes probability
#         prob2: No probability
#         end_date: Event end date
#         description: Event description
#         row: Row data from search results
#     """
#     rules = await generate_rules(question, f"Yes: {prob1}%, No: {prob2}%", end_date)
#     image_url = google_image_search(question)
#     url = await upload_image_to_s3(image_url, str(int(datetime.now().timestamp() * 1000)))
    
#     event_data = EventData(
#         is_approved=False,
#         is_child=False,
#         is_sport_page=False,
#         sport_key=None,
#         category=event['category_id'],
#         topic=event['topic_id'],
#         has_options=False,
#         title=question,
#         end_date=parse_date(end_date),
#         event_description=description,
#         rules=rules,
#         probability_of_yes=prob1,
#         probability_of_no=prob2,
#         options=None,
#         event_image=url,
#         source_link=row['Link'],
#         created_date=datetime.now()
#     )
    
#     if await save_event(event_data):
#         logging.info("Binary event saved successfully.")

# async def save_multi_option_event(event, question, options, end_date, description, row):
#     """
#     Save a multi-option event with child binary events.
    
#     Args:
#         event: Event information dictionary
#         question: Generated betting question
#         options: List of options with probabilities
#         end_date: Event end date
#         description: Event description
#         row: Row data from search results
#     """
#     rules = await generate_rules(question, options, end_date)
#     image_url = google_image_search(question)
#     url = await upload_image_to_s3(image_url, str(int(datetime.now().timestamp() * 1000)))
    
#     # Create parent event
#     event_data = EventData(
#         is_approved=False,
#         is_child=False,
#         is_sport_page=False,
#         sport_key=None,
#         category=event['category_id'],
#         topic=event['topic_id'],
#         has_options=True,
#         title=question,
#         end_date=parse_date(end_date),
#         event_description=description,
#         rules=rules,
#         probability_of_yes=None,
#         probability_of_no=None,
#         options=None,
#         event_image=url,
#         source_link=row['Link'],
#         created_date=datetime.now()
#     )
    
#     # Save parent multi-option event
#     save_response = await save_event(event_data)
#     if not save_response:
#         logging.error("Failed to save the multi-option event.")
#         return
        
#     parent_event_id = save_response['inserted_id'] if isinstance(save_response, dict) else save_response
#     updated_options = []
    
#     # Create and save binary events for each option
#     for option in options:
#         option_name = option['option']
#         option_prob = option['probability']
#         prob_yes = option_prob
#         prob_no = 100 - prob_yes
        
#         # Generate follow-up question for this option
#         binary_title = await generate_followup_question(question, option_name, description)
#         image_url = google_image_search(option_name)
#         url = await upload_image_to_s3(image_url, str(int(datetime.now().timestamp() * 1000)))
        
#         # Create child event for this option
#         binary_event_data = EventData(
#             is_approved=False,
#             is_child=True,
#             is_sport_page=False,
#             sport_key=None,
#             category=event['category_id'],
#             topic=event['topic_id'],
#             has_options=False,
#             title=binary_title,
#             end_date=parse_date(end_date),
#             event_description=description,
#             rules=await generate_rules(binary_title, f"Yes: {prob_yes}%, No: {prob_no}%", end_date),
#             probability_of_yes=prob_yes,
#             probability_of_no=prob_no,
#             options=None,
#             event_image=url,
#             source_link=row['Link'],
#             created_date=datetime.now()
#         )
        
#         # Save this child event
#         binary_save_response = await save_event(binary_event_data)
#         if binary_save_response:
#             binary_event_id = binary_save_response['inserted_id'] if isinstance(binary_save_response, dict) else binary_save_response
#             binary_event_id = ObjectId(binary_event_id) if isinstance(binary_event_id, str) else binary_event_id
            
#             # Create option reference
#             option_data = OptionData(
#                 option=option_name,
#                 probability=option_prob,
#                 market=binary_event_id
#             )
#             updated_options.append(option_data)
#         else:
#             logging.error(f"Failed to save binary event for option '{option_name}'")
    
#     # Update parent event with option references
#     if updated_options:
#         db_collection = await get_event_collection()
#         parent_id = ObjectId(parent_event_id) if isinstance(parent_event_id, str) else parent_event_id
#         update_result = await db_collection.update_one(
#             {"_id": parent_id},
#             {"$set": {"options": [opt.dict() for opt in updated_options]}}
#         )
#         if update_result.modified_count > 0:
#             logging.info(f"Parent event '{parent_event_id}' updated with options successfully.")
#         else:
#             logging.error(f"Failed to update parent event '{parent_event_id}' with options.")

# async def main():
#     """Main function to collect and process events."""
#     # Collection Phase: Build a list of events
#     subreddits = await get_categories_with_topics()
#     all_events = []
    
#     # For testing, limit to just this category
#     subreddits = {'Sports_67af0d491551b6b63d6e1d9f': ['Virat Kohali_67ce927276857b52f0869351']}
    
#     for category, topics in subreddits.items():
#         category_name, category_id_str = category.rsplit('_', 1)
#         category_id = ObjectId(category_id_str)
        
#         # Process sports events separately
#         if category_name.lower() == "sports":
#             await process_sport_events(category_name, category_id)
#             continue
            
#         # Process regular events
#         if not topics:
#             logging.info(f"No topics found for category '{category_name}'. Skipping.")
#             continue
            
#         logging.info(f"Collecting events for category: {category_name}")
#         for topic in topics:
#             try:
#                 topic_name, topic_id_str = topic.rsplit('_', 1)
#                 topic_id = ObjectId(topic_id_str)
                
#                 # Generate search query and fetch URLs
#                 subreddit = await generate_search_sentence(category_name, topic_name)
#                 logging.info(f"Searching events for topic '{topic_name}' using: {subreddit}")
#                 dataFrame = await google_search(subreddit)
                
#                 # Add each event to our collection list
#                 for index, row in dataFrame.iterrows():
#                     all_events.append({
#                         'category_name': category_name,
#                         'category_id': category_id,
#                         'topic_name': topic_name,
#                         'topic_id': topic_id,
#                         'row': row,
#                         'subreddit': subreddit
#                     })
#                 await asyncio.sleep(5)  # Pause between topics
                
#             except Exception as e:
#                 logging.exception(f"Error processing topic '{topic}' in category '{category_name}': {e}")
    
#     logging.info(f"Total collected events: {len(all_events)}")
    
#     # Process events in random order to avoid bias
#     random.shuffle(all_events)
#     for event in all_events:
#         await process_regular_event(event)
#         await asyncio.sleep(2)  # Short pause between processing
    
#     logging.info("Data extraction and processing completed.")

# if __name__ == "__main__":
#     asyncio.run(main())