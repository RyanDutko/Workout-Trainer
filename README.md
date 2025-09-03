# Workout Trainer App

A Flask-based workout tracking and AI coaching application.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the root directory with your API keys:
```bash
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Optional: Grok API Configuration (if using Grok instead of OpenAI)
# GROK_API_KEY=your_grok_api_key_here

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
```

3. Run the application:
```bash
python app.py
```

## Environment Variables

The app uses the following environment variables:

- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `GROK_API_KEY`: Your Grok API key (optional, for Grok API usage)
- `FLASK_ENV`: Flask environment (development/production)
- `FLASK_DEBUG`: Enable Flask debug mode (True/False)

## Features

- Workout logging and tracking
- Weekly workout planning
- AI-powered coaching and progression analysis
- Exercise history and analytics
- User profile and preferences management
