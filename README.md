# Prediction Market App

A robust platform for creating and managing prediction markets based on real-world events, sports data, and trending topics.

## Overview

This application automatically generates betting questions about future events by analyzing web content and sports data. It creates both binary (Yes/No) events and multi-option events with associated probabilities, rules, and descriptions.

## Features

- **Automated Event Generation**: Creates prediction market events from web search results and sports APIs
- **Multi-option Support**: Supports both binary (Yes/No) and multi-option betting markets
- **Category/Topic Organization**: Events organized by categories and topics
- **Sports Integration**: Generates events from real sports data including upcoming matches
- **Image Integration**: Automatically fetches relevant images for each event
- **Sentiment Analysis**: Uses sentiment analysis to inform probability calculations
- **AI-powered Question Generation**: Creates engaging, clear betting questions with natural language processing

## System Architecture

The application follows a modular, service-based architecture:

```
prediction-market/
│
├── .env                         # Environment variables
├── requirements.txt             # Project dependencies
├── README.md                    # Project documentation
├── main.py                      # Application entry point
│
├── app/                         # Main application code
│   ├── __init__.py              # Package initialization
│   │
│   ├── api/                     # API endpoints
│   │   ├── __init__.py
│   │   ├── routes.py            # API route definitions
│   │   ├── events.py            # Event-related endpoints
│   │   ├── markets.py           # Market-related endpoints
│   │   └── users.py             # User-related endpoints
│   │
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   └── event.py             # Event model
│   │
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   ├── search/              # Search-related services
│   │   ├── scrapers/            # Web scraping services
│   │   ├── sports/              # Sports data services
│   │   ├── ai/                  # AI services
│   │   └── storage/             # Storage services
│   │
│   ├── utils/                   # Utility functions
│   │   ├── __init__.py
│   │   ├── helper_functions.py  # General helper functions
│   │   ├── date_utils.py        # Date parsing utilities
│   │   └── prompts.py           # Prompt template utilities
│   │
│   └── config/                  # Configuration files
│       ├── __init__.py
│       ├── settings.py          # Application settings
│       └── db.py                # Database configuration
│
├── tests/                       # Test suite
└── migrations/                  # Database migrations
```

## Key Components

### Core Services

1. **GoogleSearchService**: Searches the web for event information
2. **WebScraperService**: Extracts and cleans content from web pages
3. **SportsApiService**: Fetches and processes sports data
4. **QuestionGeneratorService**: Creates betting questions and related content
5. **SentimentAnalyzerService**: Analyzes text sentiment
6. **S3StorageService**: Manages image storage

### Data Model

The platform uses MongoDB with the following main data models:

- **EventData**: Represents a prediction market event
- **OptionData**: Represents an option in a multi-option event

## Setup and Installation

### Prerequisites

- Python 3.8+
- MongoDB
- AWS S3 Bucket
- Google Custom Search API credentials
- OpenAI API key
- The Odds API key

### Environment Variables

Create a `.env` file with the following variables:

```
# API Keys
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CSE_ID=your_custom_search_engine_id
OPENAI_API_KEY=your_openai_api_key
ODDS_API_KEY=your_odds_api_key

# AWS Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=your_aws_region
AWS_BUCKET_NAME=your_s3_bucket_name

# MongoDB Settings
MONGODB_URI=your_mongodb_connection_string
DATABASE_NAME=cyrus_db
EVENT_COLLECTION=cyrus_collection

# Optional Settings
DEFAULT_MODEL=gpt-4o-mini
DEFAULT_RETRY_COUNT=3
DEFAULT_RETRY_DELAY=2
```

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/prediction-market.git
   cd prediction-market
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up your environment variables (see above)

5. Initialize the database:
   ```
   python -m app.config.db
   ```

## Usage

To run the main data collection and event generation process:

```
python main.py
```

This will:
1. Collect topics and categories from the database
2. Search for relevant content online
3. Generate betting questions from the content
4. Save events to the database

## API Endpoints

(Future implementation with examples will go here)

## Development

### Adding New Categories

To add new categories and topics, insert them into the MongoDB database:

```python
# Example for adding a new category
await db.categories.insert_one({
    "name": "Technology"
})

# Example for adding a new topic to a category
await db.topics.insert_one({
    "name": "Artificial Intelligence",
    "category": ObjectId("category_id_here")
})
```

### Testing

To run the test suite:

```
pytest tests/
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [The Odds API](https://the-odds-api.com/) for sports data
- [OpenAI](https://openai.com/) for AI-powered content generation
- [Google Custom Search API](https://developers.google.com/custom-search) for web search functionality