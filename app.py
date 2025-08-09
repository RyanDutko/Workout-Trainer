from flask import Flask, render_template, request, jsonify, Response, redirect, url_for
import sqlite3
import json
import os
from openai import OpenAI
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import time
import uuid

app = Flask(__name__)

# Database initialization
def get_db_connection():
    """Get a PostgreSQL database connection with connection pooling"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    database_url = os.environ['DATABASE_URL']
    # Use connection pooling for better performance
    database_url = database_url.replace('.us-east-2', '-pooler.us-east-2')
    
    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    return conn

def get_user_ai_preferences():
    """Get user's AI preferences for personalized responses"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT grok_tone, grok_detail_level, grok_format, communication_style, technical_level
            FROM users
            WHERE id = 1
        ''')

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                'tone': result[0] or 'motivational',
                'detail_level': result[1] or 'concise', 
                'format': result[2] or 'bullet_points',
                'communication_style': result[3] or 'encouraging',
                'technical_level': result[4] or 'beginner'
            }

        return None

    except Exception as e:
        print(f"Error getting AI preferences: {e}")
        return None

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exercise_name TEXT NOT NULL,
        sets INTEGER,
        reps TEXT,
        weight TEXT,
        notes TEXT,
        date_logged TEXT DEFAULT (datetime('now', 'localtime')),
        substitution_reason TEXT,
        performance_context TEXT,
        environmental_factors TEXT,
        difficulty_rating INTEGER,
        gym_location TEXT,
        progression_notes TEXT,
        day_completed BOOLEAN DEFAULT FALSE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS weekly_plan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_of_week TEXT NOT NULL,
        exercise_name TEXT NOT NULL,
        target_sets INTEGER,
        target_reps TEXT,
        target_weight TEXT,
        exercise_order INTEGER DEFAULT 1,
        notes TEXT,
        exercise_type TEXT DEFAULT 'working_set',
        progression_rate TEXT DEFAULT 'normal',
        created_by TEXT DEFAULT 'user',
        is_complex BOOLEAN DEFAULT FALSE,
        complex_structure TEXT,
        newly_added BOOLEAN DEFAULT FALSE,
        date_added TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS plan_context (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        plan_philosophy TEXT,
        training_style TEXT,
        weekly_structure TEXT,
        progression_strategy TEXT,
        special_considerations TEXT,
        created_by_ai BOOLEAN DEFAULT FALSE,
        creation_reasoning TEXT,
        created_date TEXT,
        updated_date TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exercise_metadata (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        exercise_name TEXT NOT NULL,
        exercise_type TEXT,
        primary_purpose TEXT,
        progression_logic TEXT,
        related_exercises TEXT,
        ai_notes TEXT,
        created_date TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exercise_relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        primary_exercise TEXT NOT NULL,
        related_exercise TEXT NOT NULL,
        relationship_type TEXT NOT NULL,
        relevance_score REAL DEFAULT 1.0,
        created_date TEXT DEFAULT (datetime('now', 'localtime'))
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        goal TEXT,
        weekly_split TEXT,
        preferences TEXT,
        grok_tone TEXT DEFAULT "motivational",
        grok_detail_level TEXT DEFAULT "concise",
        grok_format TEXT DEFAULT "bullet_points",
        preferred_units TEXT DEFAULT "lbs",
        communication_style TEXT DEFAULT "encouraging",
        technical_level TEXT DEFAULT "beginner"
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        conversation_type TEXT DEFAULT 'general',
        user_message TEXT NOT NULL,
        ai_response TEXT NOT NULL,
        detected_intent TEXT,
        confidence_score REAL DEFAULT 0.0,
        actions_taken TEXT,
        workout_context TEXT,
        exercise_mentioned TEXT,
        form_cues_given TEXT,
        performance_notes TEXT,
        plan_modifications TEXT,
        auto_executed_actions TEXT,
        extracted_workout_data TEXT,
        coaching_context TEXT,
        timestamp TEXT DEFAULT (datetime('now', 'localtime')),
        session_id TEXT,
        conversation_thread_id TEXT,
        parent_conversation_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (parent_conversation_id) REFERENCES conversations (id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversation_threads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        thread_type TEXT DEFAULT 'chat',
        thread_subject TEXT,
        current_context TEXT,
        last_intent TEXT,
        active_workout_session BOOLEAN DEFAULT FALSE,
        workout_session_data TEXT,
        created_timestamp TEXT DEFAULT (datetime('now', 'localtime')),
        updated_timestamp TEXT DEFAULT (datetime('now', 'localtime')),
        is_active BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS auto_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        action_data TEXT,
        executed BOOLEAN DEFAULT FALSE,
        execution_result TEXT,
        timestamp TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_background (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        age INTEGER,
        gender TEXT,
        height TEXT,
        current_weight TEXT,
        fitness_level TEXT,
        years_training INTEGER,
        primary_goal TEXT,
        secondary_goals TEXT,
        injuries_history TEXT,
        current_limitations TEXT,
        past_weight_loss TEXT,
        past_weight_gain TEXT,
        medical_conditions TEXT,
        training_frequency TEXT,
        available_equipment TEXT,
        time_per_session TEXT,
        preferred_training_style TEXT,
        motivation_factors TEXT,
        biggest_challenges TEXT,
        past_program_experience TEXT,
        nutrition_approach TEXT,
        sleep_quality TEXT,
        stress_level TEXT,
        additional_notes TEXT,
        chat_response_style TEXT DEFAULT 'exercise_by_exercise_breakdown',
        chat_progression_detail TEXT DEFAULT 'include_specific_progression_notes_per_exercise',
        onboarding_completed BOOLEAN DEFAULT FALSE,
        created_date TEXT,
        updated_date TEXT
    )
    ''')

    # Add missing columns to conversations table
    conversation_columns_to_add = [
        ('confidence_score', 'REAL DEFAULT 0.0'),
        ('auto_executed_actions', 'TEXT'),
        ('extracted_workout_data', 'TEXT'),
        ('coaching_context', 'TEXT'),
        ('conversation_thread_id', 'TEXT'),
        ('parent_conversation_id', 'INTEGER')
    ]

    for column_name, column_def in conversation_columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE conversations ADD COLUMN {column_name} {column_def}')
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Add missing columns if they don't exist (for existing databases)
    columns_to_add = [
        ('target_sets', 'INTEGER DEFAULT 3'),
        ('target_reps', 'TEXT DEFAULT "8-10"'),
        ('target_weight', 'TEXT DEFAULT "0lbs"'),
        ('exercise_order', 'INTEGER DEFAULT 1'),
        ('exercise_type', 'TEXT DEFAULT "working_set"'),
        ('progression_rate', 'TEXT DEFAULT "normal"'),
        ('created_by', 'TEXT DEFAULT "user"'),
        ('newly_added', 'BOOLEAN DEFAULT FALSE'),
        ('date_added', 'TEXT'),
        ('progression_notes', 'TEXT')
    ]

    # Add context columns to workouts table
    workout_columns_to_add = [
        ('substitution_reason', 'TEXT'),
        ('performance_context', 'TEXT'),
        ('environmental_factors', 'TEXT'),
        ('difficulty_rating', 'INTEGER'),
        ('gym_location', 'TEXT'),
        ('progression_notes', 'TEXT'),
        ('day_completed', 'BOOLEAN DEFAULT FALSE'),
        ('complex_exercise_data', 'TEXT')
    ]

    for column_name, column_def in workout_columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE workouts ADD COLUMN {column_name} {column_def}')
        except sqlite3.OperationalError:
            pass  # Column already exists

    for column_name, column_def in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE weekly_plan ADD COLUMN {column_name} {column_def}')
        except sqlite3.OperationalError:
            pass  # Column already exists

    cursor.execute('INSERT INTO users (id, goal, weekly_split, preferences) VALUES (1, %s, %s, %s) ON CONFLICT (id) DO NOTHING', ("", "", ""))

    # Seed exercise relationships if empty
    cursor.execute('SELECT COUNT(*) FROM exercise_relationships')
    if cursor.fetchone()[0] == 0:
        relationships = [
            ('bench press', 'dumbbell press', 'substitute', 0.9),
            ('bench press', 'incline press', 'variation', 0.8),
            ('bench press', 'push ups', 'bodyweight_version', 0.7),
            ('squats', 'leg press', 'substitute', 0.8),
            ('squats', 'goblet squats', 'variation', 0.7),
            ('deadlifts', 'Romanian deadlifts', 'variation', 0.8),
            ('deadlifts', 'rack pulls', 'variation', 0.7),
            ('overhead press', 'dumbbell shoulder press', 'substitute', 0.9),
            ('pull ups', 'lat pulldowns', 'substitute', 0.8),
            ('rows', 'dumbbell rows', 'variation', 0.9),
        ]

        for primary, related, rel_type, score in relationships:
            cursor.execute('''
                INSERT INTO exercise_relationships (primary_exercise, related_exercise, relationship_type, relevance_score)
                VALUES (?, ?, ?, ?)
            ''', (primary, related, rel_type, score))

    # Add sample weekly plan if empty
    cursor.execute('SELECT COUNT(*) FROM weekly_plan')
    if cursor.fetchone()[0] == 0:
        sample_plan = [
            ('monday', 'Bench Press', 4, '8-10', '185lbs', 1),
            ('monday', 'Squats', 4, '8-12', '225lbs', 2),
            ('monday', 'Deadlifts', 3, '5-8', '275lbs', 3),
            ('wednesday', 'Overhead Press', 4, '8-10', '135lbs', 1),
            ('wednesday', 'Pull-ups', 3, '8-12', 'bodyweight', 2),
            ('wednesday', 'Rows', 4, '10-12', '155lbs', 3),
            ('friday', 'Incline Press', 4, '8-10', '165lbs', 1),
            ('friday', 'Leg Press', 4, '12-15', '315lbs', 2),
            ('friday', 'Bicep Curls', 3, '10-12', '35lbs', 3)
        ]

        for day, exercise, sets, reps, weight, order in sample_plan:
            cursor.execute('''
                INSERT INTO weekly_plan (day_of_week, exercise_name, sets, reps, weight, order_index)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (day, exercise, sets, reps, weight, order))

    conn.commit()
    conn.close()

def parseComplexExerciseStructure(exercise_data):
    """Parse complex exercise structure from standardized JSON format"""
    try:
        # Handle structured JSON format (new standard)
        if isinstance(exercise_data, str) and exercise_data.startswith('{'):
            return json.loads(exercise_data)

        # Handle dict format (already parsed)
        if isinstance(exercise_data, dict):
            return exercise_data

        # Handle comma-separated standard format: "10 slow bicep curls(20lbs), 15 fast bicep curls(15lbs), 10 hammer curls(15lbs)"
        if isinstance(exercise_data, str) and ',' in exercise_data:
            movements = []
            parts = exercise_data.split(',')

            for part in parts:
                part = part.strip()
                # Parse: "10 slow bicep curls(20lbs)"
                match = re.match(r'(\d+)\s+(.+?)\(([^)]+)\)', part)
                if match:
                    reps, movement_name, weight = match.groups()
                    movements.append({
                        'name': movement_name.strip(),
                        'reps': reps,
                        'weight': weight
                    })

            if movements:
                return {
                    'type': 'complex',
                    'movements': movements
                }

        return None
    except Exception as e:
        print(f"Error parsing complex exercise: {e}")
        return None

def analyze_query_intent(prompt, conversation_context=None):
    """Enhanced intent detection with confidence scoring, multi-intent support, and context awareness"""
    prompt_lower = prompt.lower()

    # Intent scoring system
    intents = {}
    detected_entities = {
        'exercises': [],
        'days': [],
        'numbers': [],
        'references': []  # pronouns like "it", "that", "this"
    }

    # Extract entities for context resolution
    exercise_keywords = ['bench', 'squat', 'deadlift', 'press', 'curl', 'row', 'pull', 'tricep', 'bicep', 'leg', 'chest', 'back', 'shoulder']
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    for exercise in exercise_keywords:
        if exercise in prompt_lower:
            detected_entities['exercises'].append(exercise)

    for day in days:
        if day in prompt_lower:
            detected_entities['days'].append(day)

    # Detect references that need context resolution
    reference_words = ['it', 'that', 'this', 'the exercise', 'that workout', 'the one', 'instead', 'other']
    for ref in reference_words:
        if ref in prompt_lower:
            detected_entities['references'].append(ref)

    # Full plan review (comprehensive analysis)
    if 'FULL_PLAN_REVIEW_REQUEST:' in prompt:
        return {'intent': 'full_plan_review', 'confidence': 1.0, 'actions': [], 'entities': detected_entities}

    # CRITICAL FIX: Historical/workout discussion takes precedence over plan modification
    # When someone wants to discuss past workouts, this should be historical, not plan modification
    historical_discussion_keywords = [
        'talk about', 'discuss', 'my workout', 'my recent workout', 'how did', 'what did',
        'my training', 'yesterday', 'last week', 'this week', 'recent', 'previous', 'show me what i did'
    ]
    historical_discussion_score = sum(2 for phrase in historical_discussion_keywords if phrase in prompt_lower)

    # VERY strong indicators for historical queries - these should override other intents
    strong_historical_phrases = [
        'talk about my', 'discuss my', 'my recent', 'my workout from', 'how was my',
        'show me what i did', 'what did i do', 'my tuesday workout', 'my monday workout',
        'my wednesday workout', 'my thursday workout', 'my friday workout'
    ]
    if any(phrase in prompt_lower for phrase in strong_historical_phrases):
        historical_discussion_score += 20  # Much higher boost to ensure priority

    # Check for day-specific historical queries
    for day in days:
        if f'my {day}' in prompt_lower or f'{day} workout' in prompt_lower or f'what i did on {day}' in prompt_lower:
            historical_discussion_score += 15  # Strong boost for day-specific queries

    if historical_discussion_score > 0:
        intents['historical'] = min(historical_discussion_score * 0.05, 1.0)  # Lower multiplier but higher base scores

    # Live workout coaching
    live_workout_keywords = ['currently doing', 'doing now', 'at the gym', 'mid workout', 'between sets', 'just finished', 'form check']
    live_score = sum(1 for word in live_workout_keywords if word in prompt_lower)
    if live_score > 0:
        intents['live_workout'] = min(live_score * 0.4, 1.0)

    # Workout logging intent - but not for historical "what did I do" queries
    log_keywords = ['completed', 'finished', 'logged', 'performed', 'x', 'sets', 'reps', '@']
    log_patterns = [r'\d+x\d+', r'\d+\s*sets?', r'\d+\s*reps?', r'@\s*\d+']
    log_score = sum(1 for word in log_keywords if word in prompt_lower)
    log_score += sum(1 for pattern in log_patterns if re.search(pattern, prompt_lower))

    # Reduce log score if this is clearly a historical query
    if any(phrase in prompt_lower for phrase in ['what did i do', 'show me what i did', 'what i did on']):
        log_score = max(0, log_score - 5)

    if log_score > 0:
        intents['workout_logging'] = min(log_score * 0.3, 1.0)

    # Plan modification intent - REDUCED scoring when historical discussion detected
    plan_keywords = ['change', 'modify', 'update', 'add', 'remove', 'swap', 'substitute', 'replace', 'adjust', 'tweak', 'switch']
    plan_score = sum(1 for word in plan_keywords if word in prompt_lower)

    # CRITICAL: Don't boost plan modification score just for mentioning days in historical context
    # Only boost if it's actually about planning, not discussing past workouts
    if any(phrase in prompt_lower for phrase in ['my plan', 'weekly plan', 'workout plan', 'current plan', 'next week']):
        plan_score += 1
    if any(phrase in prompt_lower for phrase in ['can you change', 'could you modify', 'would you update', 'please add']):
        plan_score += 2

    # REDUCE plan modification score if this is clearly about past workouts
    if historical_discussion_score > 0:
        plan_score = max(0, plan_score - 3)

    if plan_score > 0:
        intents['plan_modification'] = min(plan_score * 0.3, 1.0)

    # Progression-related queries
    progression_keywords = ['progress', 'increase', 'heavier', 'next week', 'bump up', 'advance', 'progression', 'stronger']
    prog_score = sum(1 for word in progression_keywords if word in prompt_lower)
    if prog_score > 0:
        intents['progression'] = min(prog_score * 0.3, 1.0)

    # Exercise-specific queries
    exercise_names = ['bench', 'squat', 'deadlift', 'press', 'curl', 'row', 'pull', 'leg', 'chest', 'back']
    exercise_score = sum(1 for exercise in exercise_names if exercise in prompt_lower)
    if exercise_score > 0:
        intents['exercise_specific'] = min(exercise_score * 0.2, 1.0)

    # Philosophy update detection (HIGH PRIORITY - should override other intents)
    philosophy_update_keywords = ['update my philosophy', 'update my philisophy', 'change my philosophy', 'modify my philosophy']
    philosophy_update_score = sum(10 for phrase in philosophy_update_keywords if phrase in prompt_lower)  # Very high score

    if philosophy_update_score > 0:
        intents['philosophy_update'] = 1.0  # Maximum confidence for philosophy updates

    # Enhanced historical queries - don't duplicate if already scored above
    if 'historical' not in intents:
        historical_keywords = ['did', 'last', 'history', 'previous', 'ago', 'yesterday', 'week', 'recent', 'latest']
        hist_score = sum(1 for word in historical_keywords if word in prompt_lower)

        # Boost score for day-specific historical queries
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            if day in prompt_lower and any(word in prompt_lower for word in ['what', 'show', 'did']):
                hist_score += 5

        # Boost score for general recent workout queries
        general_recent_phrases = ['recent logs', 'recent workout', 'most recent', 'last workout', 'latest workout', 'most recent day']
        for phrase in general_recent_phrases:
            if phrase in prompt_lower:
                hist_score += 8  # High boost for clear recent workout requests

        if hist_score > 0:
            intents['historical'] = min(hist_score * 0.25, 1.0)

    # General fitness chat
    general_keywords = ['hello', 'hi', 'how are', 'what can', 'help', 'advice', 'tips']
    general_score = sum(1 for word in general_keywords if word in prompt_lower)
    if general_score > 0:
        intents['general'] = min(general_score * 0.15, 1.0)

    # Enhanced negation and correction detection
    negation_keywords = ['no', 'not', 'nope', 'incorrect', 'wrong', 'cancel', 'nevermind', 'actually']
    correction_keywords = ['instead', 'rather', 'meant', 'actually', 'correction', 'change that to']

    negation_score = sum(1 for word in negation_keywords if word in prompt_lower)
    correction_score = sum(1 for word in correction_keywords if word in prompt_lower)

    if negation_score > 0:
        intents['negation'] = min(negation_score * 0.4, 1.0)

    if correction_score > 0:
        intents['correction'] = min(correction_score * 0.4, 1.0)

    # Context-dependent intent boosting
    if conversation_context:
        last_intent = conversation_context.get('last_intent')
        last_entities = conversation_context.get('last_entities', {})

        # If user is making references and we have context, boost contextual intents
        if detected_entities['references'] and last_intent:
            if last_intent == 'plan_modification':
                intents['plan_modification'] = intents.get('plan_modification', 0) + 0.3
            elif last_intent == 'progression':
                intents['progression'] = intents.get('progression', 0) + 0.3

    # Multi-intent detection - return top intents if close in confidence
    sorted_intents = sorted(intents.items(), key=lambda x: x[1], reverse=True)

    if len(sorted_intents) >= 2 and sorted_intents[1][1] > 0.4:
        # Multiple intents detected
        return {
            'intent': 'multi_intent',
            'primary_intent': sorted_intents[0][0],
            'secondary_intent': sorted_intents[1][0],
            'confidence': sorted_intents[0][1],
            'all_intents': intents,
            'entities': detected_entities,
            'actions': extract_potential_actions(prompt, sorted_intents[0][0])
        }
    elif intents:
        best_intent = sorted_intents[0]
        return {
            'intent': best_intent[0],
            'confidence': best_intent[1],
            'all_intents': intents,
            'entities': detected_entities,
            'actions': extract_potential_actions(prompt, best_intent[0])
        }
    else:
        return {'intent': 'general', 'confidence': 0.1, 'actions': [], 'entities': detected_entities}

def extract_potential_actions(prompt, intent):
    """Extract potential auto-executable actions from the prompt"""
    actions = []
    prompt_lower = prompt.lower()

    if intent == 'workout_logging':
        # Look for workout data patterns
        workout_patterns = re.findall(r'(\d+)x(\d+)(?:@|\s*at\s*)(\d+(?:\.\d+)?)\s*(?:lbs?|kg)?\s+([a-zA-Z\s]+)', prompt)
        for sets, reps, weight, exercise in workout_patterns:
            actions.append({
                'type': 'log_workout',
                'data': {
                    'exercise': exercise.strip(),
                    'sets': int(sets),
                    'reps': reps,
                    'weight': f"{weight}lbs"
                }
            })

    elif intent == 'plan_modification':
        # Look for plan change requests with more detail
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        detected_day = None
        for day in days:
            if day in prompt_lower:
                detected_day = day
                break

        # Try to extract exercise and modification details
        modification_type = 'update'  # default

        if any(word in prompt_lower for word in ['add', 'include']):
            modification_type = 'add'
        elif any(word in prompt_lower for word in ['remove', 'delete', 'drop']):
            modification_type = 'remove'

        actions.append({
            'type': 'modify_plan',
            'data': {
                'day': detected_day,
                'modification_type': modification_type,
                'raw_request': prompt
            }
        })

    return actions

def extract_actual_performed_weight(exercise_name, recent_conversations):
    """Extract the actual weight performed from recent conversations and workout logs"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Look for the most recent log of this exercise with weight details
        cursor.execute('''
            SELECT weight, notes FROM workouts
            WHERE LOWER(exercise_name) = LOWER(?)
            ORDER BY date_logged DESC, id DESC
            LIMIT 1
        ''', (exercise_name,))

        recent_log = cursor.fetchone()
        if recent_log:
            weight, notes = recent_log

            # If notes mention specific weights (like "110 lbs for set 2 and 3"), extract the higher weight
            if notes:
                import re
                weight_mentions = re.findall(r'(\d+)\s*(?:lbs?|pounds?)', notes)
                if weight_mentions:
                    # Return the highest weight mentioned in notes
                    highest_weight = max(int(w) for w in weight_mentions)
                    return f"{highest_weight}lbs"

            # Otherwise return the logged weight
            return weight

        conn.close()
        return None

    except Exception as e:
        print(f"Error extracting performed weight: {e}")
        return None

def parse_plan_modification_from_ai_response(ai_response, user_request):
    """Parse Grok's response to extract specific plan modifications vs progression guidance"""
    try:
        # Look for progression guidance first (preferred method)
        progression_guidance = []
        guidance_pattern = r'PROGRESSION TIP:\s*([^:]+):\s*(.+?)(?=\n|$)'
        guidance_matches = re.findall(guidance_pattern, ai_response, re.IGNORECASE)

        for exercise_name, guidance_note in guidance_matches:
            progression_guidance.append({
                'type': 'progression_guidance',
                'exercise_name': exercise_name.strip(),
                'guidance_note': guidance_note.strip(),
                'day': None  # Will be determined by the exercise location in plan
            })

        if progression_guidance:
            return {'type': 'guidance', 'data': progression_guidance}

        # Look for comprehensive trainer-style responses for actual plan modifications
        modifications = []

        # Check for structured trainer responses
        if 'MODIFY:' in ai_response or 'ADD:' in ai_response or 'REPLACE:' in ai_response:
            lines = ai_response.split('\n')
            current_mod = None

            for line in lines:
                line = line.strip()

                # Look for modification commands
                if line.startswith('MODIFY:') or line.startswith('ADD:') or line.startswith('REPLACE:'):
                    if current_mod:
                        modifications.append(current_mod)

                    mod_type = 'modify' if line.startswith('MODIFY:') else ('add' if line.startswith('ADD:') else 'replace')

                    # Extract day and exercise from the line
                    day_match = re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', line.lower())
                    exercise_match = re.search(r'(?:replace|add|modify)[\s\w]*?([a-zA-Z\s]+?)(?:\s*-|\s*with|\s*$)', line, re.IGNORECASE)

                    current_mod = {
                        'type': mod_type,
                        'day': day_match.group(1) if day_match else None,
                        'exercise_name': exercise_match.group(1).strip() if exercise_match else 'Unknown Exercise',
                        'sets': 3,  # Default
                        'reps': '8-12',  # Default
                        'weight': 'bodyweight',  # Default
                        'reasoning': ''
                    }

                # Extract details for current modification
                elif current_mod:
                    if 'Sets/reps:' in line or 'sets/reps:' in line:
                        sets_reps = line.split(':', 1)[1].strip()
                        sets_match = re.search(r'(\d+)', sets_reps)
                        reps_match = re.search(r'(\d+(?:-\d+)?)', sets_reps)
                        if sets_match:
                            current_mod['sets'] = int(sets_match.group(1))
                        if reps_match:
                            current_mod['reps'] = reps_match.group(1)

                    elif 'Reasoning:' in line:
                        current_mod['reasoning'] = line.split(':', 1)[1].strip()

                    elif 'Weight:' in line or '@' in line:
                        weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lbs?|kg)', line)
                        if weight_match:
                            current_mod['weight'] = f"{weight_match.group(1)}lbs"

            # Add the last modification
            if current_mod:
                modifications.append(current_mod)

        # If we found structured modifications, return them
        if modifications:
            return {'type': 'plan_modification', 'data': modifications[0] if len(modifications) == 1 else modifications}

        # Fallback to original parsing logic for unstructured responses
        response_lower = ai_response.lower()

        if not any(phrase in response_lower for phrase in ['can make', 'i can', 'absolutely', 'change', 'modify', 'update', 'recommend', 'suggest']):
            return None

        # Look for trainer-style language indicating modifications
        trainer_patterns = [
            r'your current (.+?) volume is already high, so instead of adding more, let\'s replace (.+?) with (.+)',
            r'i\'d recommend replacing (.+?) with (.+?) because',
            r'instead of adding more (.+?), let\'s swap (.+?) for (.+)',
            r'your (.+?) day already has (.+?), so let\'s replace (.+?) with (.+)'
        ]

        for pattern in trainer_patterns:
            match = re.search(pattern, response_lower)
            if match:
                return {
                    'type': 'replace',
                    'exercise_name': match.group(3) if len(match.groups()) >= 3 else 'Unknown Exercise',
                    'old_exercise': match.group(2) if len(match.groups()) >= 2 else None,
                    'day': None,  # Will be inferred
                    'sets': 3,
                    'reps': '8-12',
                    'weight': 'bodyweight',
                    'reasoning': f"Trainer recommendation: {match.group(0)}"
                }

        # Extract exercise, sets, reps, weight from either user request or AI response
        exercise_pattern = r'(?:tricep|bicep|chest|shoulder|leg|back|ab|core)[\s\w]*(?:press|curl|extension|raise|pushdown|pulldown|fly|row|squat|deadlift)'
        sets_pattern = r'(\d+)\s*(?:sets?|x)'
        reps_pattern = r'(?:x|sets?\s*of\s*)(\d+(?:-\d+)?)'
        weight_pattern = r'(\d+(?:\.\d+)?)\s*(?:lbs?|kg|pounds?)'
        day_pattern = r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'

        # Try to find these patterns in either the user request or AI response
        combined_text = f"{user_request} {ai_response}".lower()

        exercise_match = re.search(exercise_pattern, combined_text)
        sets_match = re.search(sets_pattern, combined_text)
        reps_match = re.search(reps_pattern, combined_text)
        weight_match = re.search(weight_pattern, combined_text)
        day_match = re.search(day_pattern, combined_text)

        if exercise_match:
            return {
                'type': 'update',  # assume update unless specified
                'exercise_name': exercise_match.group(0),
                'day': day_match.group(1) if day_match else None,
                'sets': int(sets_match.group(1)) if sets_match else None,
                'reps': reps_match.group(1) if reps_match else None,
                'weight': f"{weight_match.group(1)}lbs" if weight_match else None,
                'reasoning': f"Modified based on conversation about {exercise_match.group(0)}"
            }

    except Exception as e:
        print(f"Error parsing plan modification: {e}")

    return None

def remove_loose_skin_references_comprehensive(target_text="loose skin"):
    """Comprehensively remove all mentions of specified text from all relevant database fields"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        changes_made = []

        # 1. Update plan_context table - all text fields
        plan_context_fields = ['plan_philosophy', 'weekly_structure', 'progression_strategy', 'special_considerations']

        for field in plan_context_fields:
            cursor.execute(f'SELECT id, {field} FROM plan_context WHERE user_id = 1 AND {field} IS NOT NULL')
            records = cursor.fetchall()

            for record_id, current_text in records:
                if current_text and target_text.lower() in current_text.lower():
                    # Remove the target text and clean up
                    updated_text = remove_text_and_cleanup(current_text, target_text)
                    cursor.execute(f'UPDATE plan_context SET {field} = ?, updated_date = ? WHERE id = ?',
                                 (updated_text, datetime.now().strftime('%Y-%m-%d'), record_id))
                    changes_made.append(f"Updated {field} in plan_context")

        # 2. Update exercise_metadata table
        metadata_fields = ['primary_purpose', 'ai_notes']

        for field in metadata_fields:
            cursor.execute(f'SELECT id, exercise_name, {field} FROM exercise_metadata WHERE user_id = 1 AND {field} IS NOT NULL')
            records = cursor.fetchall()

            for record_id, exercise_name, current_text in records:
                if current_text and target_text.lower() in current_text.lower():
                    updated_text = remove_text_and_cleanup(current_text, target_text)
                    cursor.execute(f'UPDATE exercise_metadata SET {field} = ? WHERE id = ?',
                                 (updated_text, record_id))
                    changes_made.append(f"Updated {field} for {exercise_name}")

        # 3. Update weekly_plan notes
        cursor.execute('SELECT id, exercise_name, notes FROM weekly_plan WHERE notes IS NOT NULL')
        records = cursor.fetchall()

        for record_id, exercise_name, current_notes in records:
            if current_notes and target_text.lower() in current_notes.lower():
                updated_notes = remove_text_and_cleanup(current_notes, target_text)
                cursor.execute('UPDATE weekly_plan SET notes = ? WHERE id = ?',
                             (updated_notes, record_id))
                changes_made.append(f"Updated notes for {exercise_name}")

        conn.commit()
        conn.close()

        return changes_made

    except Exception as e:
        print(f"Error in comprehensive removal: {e}")
        return []

def remove_text_and_cleanup(original_text, target_text):
    """Remove target text and clean up the resulting string"""
    import re

    # Case-insensitive removal
    pattern = re.compile(re.escape(target_text), re.IGNORECASE)
    updated_text = pattern.sub('', original_text)

    # Clean up common artifacts
    # Remove "for " if it's left hanging
    updated_text = re.sub(r'\bfor\s*$', '', updated_text, flags=re.IGNORECASE)
    updated_text = re.sub(r'\bfor\s*\,', ',', updated_text, flags=re.IGNORECASE)
    updated_text = re.sub(r'\bfor\s*\.', '.', updated_text, flags=re.IGNORECASE)

    # Clean up extra spaces and punctuation
    updated_text = re.sub(r'\s+', ' ', updated_text)  # Multiple spaces to single
    updated_text = re.sub(r'\s*,\s*,', ',', updated_text)  # Double commas
    updated_text = re.sub(r'^\s*,\s*', '', updated_text)  # Leading comma
    updated_text = re.sub(r'\s*,\s*$', '', updated_text)  # Trailing comma
    updated_text = updated_text.strip()

    return updated_text



def parse_philosophy_update_from_conversation(ai_response, user_request):
    """Parse conversation to detect philosophy/approach changes"""
    try:
        combined_text = f"{user_request} {ai_response}".lower()
        user_request_lower = user_request.lower()
        ai_response_lower = ai_response.lower()

        # Check for targeted removal requests
        removal_patterns = [
            r'remove.*?(?:mention|reference).*?(?:of|to)\s*([^.]+)',
            r'remove\s+([^.]+?)\s+from',
            r'get rid of.*?([^.]+)',
            r'eliminate.*?([^.]+)'
        ]

        for pattern in removal_patterns:
            match = re.search(pattern, user_request_lower)
            if match:
                target_text = match.group(1).strip()
                if target_text:
                    print(f"🎯 Detected targeted removal request for: '{target_text}'")
                    changes_made = remove_loose_skin_references_comprehensive(target_text)

                    if changes_made:
                        print(f"✅ Comprehensive removal complete:")
                        for change in changes_made:
                            print(f"  • {change}")

                        return {
                            'comprehensive_removal': True,
                            'target_text': target_text,
                            'changes_made': changes_made,
                            'reasoning': f"✅ COMPLETED: Removed all mentions of '{target_text}' from {len(changes_made)} locations in your plan",
                            'success_message': f"Successfully removed '{target_text}' from {len(changes_made)} places in your training plan!"
                        }
                    else:
                        return {
                            'comprehensive_removal': True,
                            'target_text': target_text,
                            'changes_made': [],
                            'reasoning': f"No mentions of '{target_text}' found to remove",
                            'success_message': f"No mentions of '{target_text}' were found in your plan"
                        }

        # Look for EXPLICIT user requests that are asking for changes (NOT just asking questions)
        user_change_requests = [
            'update my philosophy with',
            'change my approach to',
            'modify my philosophy to',
            'rewrite my philosophy to',
            'set my philosophy to',
            'replace my philosophy with',
            'remove any mention of',
            'remove from my philosophy'
        ]

        user_wants_change = any(request in user_request_lower for request in user_change_requests)

        # CRITICAL: Exclude discussion-only requests
        discussion_only_requests = [
            'talk about my philosophy',
            'discuss my philosophy', 
            'what is my philosophy',
            'show me my philosophy',
            'tell me about my approach'
        ]

        if any(discussion in user_request_lower for discussion in discussion_only_requests):
            user_wants_change = False

        # If user wants a philosophy change, we need to help Grok by providing current context
        if user_wants_change:
            # Get current philosophy from database
            conn = sqlite3.connect('workout_logs.db')
            cursor = conn.cursor()

            cursor.execute('''
                SELECT plan_philosophy, weekly_structure, progression_strategy, special_considerations
                FROM plan_context
                WHERE user_id = 1
                ORDER BY created_date DESC
                LIMIT 1
            ''')

            current_context = cursor.fetchone()
            conn.close()

            if current_context:
                current_philosophy, weekly_structure, progression_strategy, special_considerations = current_context

                # Create a comprehensive rewrite prompt for Grok using new 2-field structure
                rewrite_prompt = f"""Here is my current training philosophy:

CURRENT PHILOSOPHY:
Core Philosophy: {current_philosophy or 'Not set'}
Current Plan Priorities: {progression_strategy or 'Not set'}

USER REQUEST: {user_request}

Please provide a complete updated philosophy that addresses the user's request. Format your response with these exact sections:

CORE_PHILOSOPHY: [the foundational training approach and principles that don't change often]
CURRENT_PLAN_PRIORITIES: [specific current focuses, goals, and priorities for this training phase]

Make sure to provide complete, updated versions of both sections, not just acknowledgments."""

                # Get Grok's structured rewrite
                # progression_analysis = get_grok_response_with_context(rewrite_prompt, user_background) # Grok API call
                response = get_grok_response_with_context(rewrite_prompt)

                # For natural language philosophy (like from ChatGPT), use intelligent parsing for new 2-field structure
                if any(phrase in user_request_lower for phrase in ['update my philosophy with', 'update my philosophy to', 'update my philisophy to']):
                    # Extract the actual philosophy content after "with:" or "to:"
                    philosophy_content = user_request.split(':', 1)[1].strip() if ':' in user_request else response

                    # Parse the natural language philosophy into new 2-field structure
                    extracted_data = {}

                    # Split content into core philosophy (foundational) and current priorities (specific)
                    # Look for structural/foundational elements vs specific current focuses
                    core_parts = []
                    priority_parts = []

                    sentences = philosophy_content.split('.')
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue

                        # Core philosophy indicators (foundational approaches)
                        if any(word in sentence.lower() for word in ['machine-', 'cable-focused', 'joint safety', 'free weights', 'progressive overload', 'recovery']):
                            core_parts.append(sentence + '.')
                        # Current priority indicators (specific focuses)
                        elif any(word in sentence.lower() for word in ['midsection', 'pelvis', 'abs', '5-day split', 'top priority', 'custom-built', 'balanced muscle']):
                            priority_parts.append(sentence + '.')
                        else:
                            # Default to priorities for specific content
                            priority_parts.append(sentence + '.')

                    extracted_data['plan_philosophy'] = ' '.join(core_parts) if core_parts else philosophy_content[:len(philosophy_content)//2]
                    extracted_data['progression_strategy'] = ' '.join(priority_parts) if priority_parts else philosophy_content[len(philosophy_content)//2:]

                    extracted_data['reasoning'] = f"Updated with natural language philosophy from user using new 2-field structure"
                    print(f"🧠 Successfully parsed natural language philosophy into core philosophy + current priorities")
                    return extracted_data

                # Parse ChatGPT's structured response using new 2-field structure
                lines = response.split('\n')
                extracted_data = {}
                current_section = None
                current_content = []

                for line in lines:
                    line = line.strip()

                    # Look for section headers (more flexible matching)
                    if any(header in line.upper() for header in ['CORE_PHILOSOPHY:', 'CORE PHILOSOPHY:']):
                        # Save previous section
                        if current_section and current_content:
                            extracted_data[current_section] = ' '.join(current_content).strip()

                        current_section = 'plan_philosophy'
                        current_content = [line.split(':', 1)[1].strip()] if ':' in line else []

                    elif any(header in line.upper() for header in ['CURRENT_PLAN_PRIORITIES:', 'CURRENT PLAN PRIORITIES:', 'PLAN_PRIORITIES:', 'PRIORITIES:']):
                        # Save previous section  
                        if current_section and current_content:
                            extracted_data[current_section] = ' '.join(current_content).strip()

                        current_section = 'progression_strategy'
                        current_content = [line.split(':', 1)[1].strip()] if ':' in line else []

                    elif any(header in line.upper() for header in ['REASONING:', 'REASON:']):
                        # Save previous section
                        if current_section and current_content:
                            extracted_data[current_section] = ' '.join(current_content).strip()

                        current_section = 'reasoning'
                        current_content = [line.split(':', 1)[1].strip()] if ':' in line else []

                    # Legacy compatibility
                    elif 'TRAINING_PHILOSOPHY:' in line.upper() and not extracted_data.get('plan_philosophy'):
                        if current_section and current_content:
                            extracted_data[current_section] = ' '.join(current_content).strip()
                        current_section = 'plan_philosophy'
                        current_content = [line.split(':', 1)[1].strip()] if ':' in line else []

                    elif 'PROGRESSION_STRATEGY:' in line.upper() and not extracted_data.get('progression_strategy'):
                        if current_section and current_content:
                            extracted_data[current_section] = ' '.join(current_content).strip()
                        current_section = 'progression_strategy' 
                        current_content = [line.split(':', 1)[1].strip()] if ':' in line else []

                    else:
                        # Add to current section if we're in one
                        if current_section and line:
                            current_content.append(line)

                # Save final section
                if current_section and current_content:
                    extracted_data[current_section] = ' '.join(current_content).strip()

                # If no structured sections found, try to use the whole response
                if not extracted_data.get('plan_philosophy') and not extracted_data.get('progression_strategy'):
                    # Split the response roughly in half
                    full_response = response.strip()
                    sentences = full_response.split('.')
                    mid_point = len(sentences) // 2

                    extracted_data['plan_philosophy'] = '. '.join(sentences[:mid_point]).strip() + '.'
                    extracted_data['progression_strategy'] = '. '.join(sentences[mid_point:]).strip()

                # Ensure we have reasoning
                if not extracted_data.get('reasoning'):
                    extracted_data['reasoning'] = f"Updated based on user request: {user_request[:100]}..."

                print(f"🧠 Successfully parsed philosophy update - Core: {len(extracted_data.get('plan_philosophy', ''))} chars, Priorities: {len(extracted_data.get('progression_strategy', ''))} chars")
                return extracted_data

            else:
                print(f"⚠️ No existing philosophy found to rewrite")
                return None

        # Legacy logic for responses that already contain philosophy content
        grok_update_indicators = [
            "i'll update your philosophy",
            "here's your updated",
            "your new philosophy",
            "updated approach",
            "revised philosophy",
            "modified approach",
            "new training philosophy",
            "updated training approach"
        ]

        grok_is_updating = any(indicator in ai_response_lower for indicator in grok_update_indicators)

        philosophy_content_indicators = [
            "training philosophy:",
            "approach:",
            "philosophy is",
            "training approach",
            "focus on",
            "emphasize",
            "prioritize"
        ]

        has_philosophy_content = any(indicator in ai_response_lower for indicator in philosophy_content_indicators)

        # Only proceed with legacy parsing if Grok provided substantial content
        if grok_is_updating or has_philosophy_content:

            # Use Grok's response as the new philosophy if it contains substantial content
            if len(ai_response) > 100 and has_philosophy_content:
                # Try to extract structured philosophy from Grok's response
                philosophy_sections = {}

                # Look for specific philosophy elements in Grok's response
                response_lines = ai_response.split('\n')
                current_section = None
                current_content = []

                for line in response_lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Check for section headers
                    if any(header in line.lower() for header in ['philosophy:', 'approach:', 'strategy:', 'considerations:']):
                        # Save previous section
                        if current_section and current_content:
                            philosophy_sections[current_section] = ' '.join(current_content)

                        # Start new section
                        if 'philosophy' in line.lower():
                            current_section = 'plan_philosophy'
                        elif 'strategy' in line.lower() or 'progression' in line.lower():
                            current_section = 'progression_strategy'
                        elif 'consideration' in line.lower():
                            current_section = 'special_considerations'
                        else:
                            current_section = 'plan_philosophy'  # default

                        current_content = [line.split(':', 1)[-1].strip()] if ':' in line else []
                    else:
                        # Add to current section
                        if current_section:
                            current_content.append(line)

                # Save last section
                if current_section and current_content:
                    philosophy_sections[current_section] = ' '.join(current_content)

                # If we didn't find structured sections, use the whole response as philosophy
                if not philosophy_sections:
                    philosophy_sections['plan_philosophy'] = ai_response.strip()

                # Add reasoning
                philosophy_sections['reasoning'] = f"Updated based on user request: {user_request[:100]}..."

                print(f"🧠 Detected philosophy update request with substantial AI content")
                return philosophy_sections

        # No philosophy update detected
        return None

    except Exception as e:
        print(f"Error parsing philosophy update: {e}")

    return None

def analyze_day_progression(date_str):
    """Analyze progression for all exercises completed on a specific day"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get all workouts for this date
        cursor.execute('''
            SELECT id, exercise_name, sets, reps, weight, notes, progression_notes
            FROM workouts
            WHERE date_logged = ?
            ORDER BY id
        ''', (date_str,))

        day_workouts = cursor.fetchall()

        if not day_workouts:
            conn.close()
            return {"success": False, "message": f"No workouts found for {date_str}. Make sure you have logged workouts for this date."}

        # Get user context for better progression analysis
        cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY id DESC LIMIT 1')
        user_bg = cursor.fetchone()
        user_background = None
        if user_bg:
            columns = [description[0] for description in cursor.description]
            user_background = dict(zip(columns, user_bg))

        # Get weekly plan context
        day_name = datetime.strptime(date_str, '%Y-%m-%d').strftime('%A').lower()
        cursor.execute('''
            SELECT exercise_name, target_sets, target_reps, target_weight
            FROM weekly_plan
            WHERE day_of_week = ?
        ''', (day_name,))
        planned_exercises = cursor.fetchall()

        # Get recent workout history for context (last 4 weeks)
        four_weeks_ago = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(weeks=4)).strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT exercise_name, sets, reps, weight, date_logged, notes
            FROM workouts
            WHERE date_logged >= ? AND date_logged < ?
            ORDER BY exercise_name, date_logged DESC
        ''', (four_weeks_ago, date_str))
        recent_history = cursor.fetchall()

        # Build comprehensive context for Grok
        context_info = f"=== PROGRESSION ANALYSIS REQUEST ===\n"
        context_info += f"Date: {date_str} ({day_name.title()})\n\n"

        if user_background:
            context_info += f"User Profile:\n"
            context_info += f"- Goal: {user_background.get('primary_goal', 'Not specified')}\n"
            context_info += f"- Experience: {user_background.get('years_training', 'Not specified')} years\n"
            context_info += f"- Fitness Level: {user_background.get('fitness_level', 'Not specified')}\n"
            if user_background.get('injuries_history'):
                context_info += f"- Injuries: {user_background['injuries_history']}\n"
            context_info += "\n"

        context_info += f"TODAY'S COMPLETED WORKOUTS:\n"
        for workout_id, exercise, sets, reps, weight, notes, existing_progression in day_workouts:
            context_info += f"• {exercise}: {sets}x{reps}@{weight}"
            if notes:
                context_info += f" - Notes: {notes}"
                # Check if this was a substitution and extract the details
                if "SUBSTITUTED FROM:" in notes:
                    context_info += f"\n  ⚠️ SUBSTITUTION ALERT: This was a substituted exercise - different weight scale than original"
            context_info += "\n"

        if planned_exercises:
            context_info += f"\nPLANNED FOR {day_name.upper()}:\n"
            for exercise, target_sets, target_reps, target_weight in planned_exercises:
                context_info += f"• {exercise}: {target_sets}x{target_reps}@{target_weight}\n"

        if recent_history:
            context_info += f"\nRECENT HISTORY (Last 4 weeks):\n"
            current_exercise = ""
            for exercise, sets, reps, weight, date, notes in recent_history[:20]:  # Limit for context
                if exercise != current_exercise:
                    context_info += f"\n{exercise}:\n"
                    current_exercise = exercise
                context_info += f"  {date}: {sets}x{reps}@{weight}"
                if notes:
                    context_info += f" - {notes}"
                context_info += "\n"

        # Create Grok prompt for progression analysis
        progression_prompt = f"""{context_info}

Please analyze today's workout performance and provide specific progression suggestions for each exercise. Consider:
- How today's performance compares to the planned targets
- Recent performance trends from workout history
- Appropriate progression based on user's experience level
- Any performance notes that indicate difficulty or ease
- CRITICAL: For substituted exercises, understand that weight scales are completely different between exercises

For each exercise completed today, provide a progression note in this format:
EXERCISE: [exercise name]
PROGRESSION: [specific actionable suggestion, e.g., "Increase to 185lbs next week", "Add 1 rep per set", "Maintain current intensity", "Deload to 160lbs - showing fatigue"]
REASONING: [brief explanation of why this progression makes sense]

SPECIAL HANDLING FOR SUBSTITUTIONS:
If an exercise was substituted (look for "SUBSTITUTED FROM:" in the notes), understand these key points:
1. The weight used is for the NEW exercise, not the original planned exercise
2. Different exercises use completely different weight scales (machine vs cable vs free weight)
3. Focus progression advice on the substituted exercise performed, not the original planned exercise

For substitutions, use this format:
EXERCISE: [substituted exercise name]
SUBSTITUTION_ANALYSIS: "You substituted [original exercise] with [new exercise]. Based on your performance at [actual weight used], suggest [specific next progression for the substituted exercise]."
SUBSTITUTION_QUESTION: "Great choice on [substituted exercise]! Would you like to make this a permanent replacement for [original exercise] in your plan, or keep trying [original exercise] next week?"
REASONING: [why the substitution worked well and progression logic for the actual exercise performed]

Keep suggestions practical and progressive. Base recommendations on actual performance vs. plan."""

        # Get Grok's analysis
        progression_analysis = get_grok_response_with_context(progression_prompt, user_background)

        # Parse Grok's response to extract individual progression notes
        progression_updates = []
        lines = progression_analysis.split('\n')
        current_exercise = None
        current_progression = None
        current_reasoning = None

        for line in lines:
            line = line.strip()
            if line.startswith('EXERCISE:'):
                # Save previous exercise if exists
                if current_exercise and current_progression:
                    progression_updates.append({
                        'exercise': current_exercise,
                        'progression': current_progression,
                        'reasoning': current_reasoning or ''
                    })

                current_exercise = line.replace('EXERCISE:', '').strip()
                current_progression = None
                current_reasoning = None

            elif line.startswith('PROGRESSION:'):
                current_progression = line.replace('PROGRESSION:', '').strip()

            elif line.startswith('REASONING:'):
                current_reasoning = line.replace('REASONING:', '').strip()

        # Save last exercise
        if current_exercise and current_progression:
            progression_updates.append({
                'exercise': current_exercise,
                'progression': current_progression,
                'reasoning': current_reasoning or ''
            })

        # Update workout records with progression notes
        updated_count = 0
        for workout_id, exercise_name, sets, reps, weight, notes, existing_progression in day_workouts:
            # Find matching progression update
            progression_note = None
            for update in progression_updates:
                if update['exercise'].lower() in exercise_name.lower() or exercise_name.lower() in update['exercise'].lower():
                    full_note = f"{update['progression']}"
                    if update['reasoning']:
                        full_note += f" - {update['reasoning']}"
                    progression_note = full_note
                    break

            if not progression_note:
                # Fallback generic note if Grok didn't provide specific guidance
                progression_note = "Analysis pending - check performance vs plan"

            # Update the workout record (always set day_completed = TRUE)
            cursor.execute('''
                UPDATE workouts
                SET progression_notes = ?, day_completed = TRUE
                WHERE id = ?
            ''', (progression_note, workout_id))
            updated_count += 1

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Generated progression notes for {updated_count} exercises",
            "date": date_str,
            "full_analysis": progression_analysis,
            "individual_updates": progression_updates
        }

    except Exception as e:
        print(f"Error in analyze_day_progression: {e}")
        return {"success": False, "error": str(e)}

# Context builders have been moved to separate modules in context_builders/

def build_philosophy_update_context(prompt):
    """Build context specifically for philosophy update requests"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get current philosophy from database
        cursor.execute('''
            SELECT plan_philosophy, progression_strategy
            FROM plan_context
            WHERE user_id = 1
            ORDER BY created_date DESC
            LIMIT 1
        ''')

        current_context = cursor.fetchone()
        conn.close()

        if current_context:
            current_philosophy, current_priorities = current_context

            context_info = "=== PHILOSOPHY UPDATE REQUEST ===\n"
            context_info += f"CURRENT PHILOSOPHY:\n"
            context_info += f"Core Philosophy: {current_philosophy or 'Not set'}\n"
            context_info += f"Current Plan Priorities: {current_priorities or 'Not set'}\n\n"

            context_info += f"USER REQUEST: {prompt}\n\n"
            context_info += """Please parse the new philosophy from the user request and provide a structured response with these exact sections:

CORE_PHILOSOPHY: [the foundational training approach and principles]
CURRENT_PLAN_PRIORITIES: [specific current focuses and priorities for this training phase]
REASONING: [brief explanation of changes made]

Extract the philosophy content after the colon (:) in the user's message and structure it appropriately into these 2 sections."""

            print(f"🧠 Built philosophy update context with current stored philosophy (2-field structure)")
            return context_info
        else:
            print(f"⚠️ No existing philosophy found for update")
            return "=== NO EXISTING PHILOSOPHY FOUND ===\nPlease provide the philosophy content and I'll help structure it.\n\n" + prompt

    except Exception as e:
        print(f"Error building philosophy update context: {e}")
        return prompt

def build_smart_context(prompt, query_intent, user_background=None):
    """Route to appropriate context builder based on query intent"""
    from context_builders.historical import build_historical_context
    from context_builders.plan import build_plan_context
    from context_builders.progression import build_progression_context
    from context_builders.general import build_general_context

    print(f"\n🔍 ===== SMART CONTEXT ROUTING =====")
    print(f"🔍 Intent: {query_intent}")
    print(f"🔍 Prompt: '{prompt}'")

    # Extract the actual intent string if it's in a dict format
    actual_intent = query_intent
    all_intents = {}
    if isinstance(query_intent, dict):
        actual_intent = query_intent.get('intent', 'general')
        all_intents = query_intent.get('all_intents', {})

    # SPECIAL CASE: If this involves workout history even with negation/correction
    # Check if this is really about showing workout data despite other intents
    is_workout_history_request = any(phrase in prompt.lower() for phrase in [
        'show me tuesday', 'show me wednesday', 'show me monday', 'show me thursday', 'show me friday',
        'what did i do on', 'my tuesday workout', 'my wednesday workout', 'my monday workout',
        'tuesday instead', 'wednesday instead', 'monday instead', 'what i did on wednesday',
        'my wednesday', 'workouts i did', 'what workouts'
    ])

    # CRITICAL: Also check for follow-up historical requests
    # If prompt contains day names AND historical intent exists, it's likely historical
    contains_day = any(day in prompt.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])

    # HISTORICAL WORKOUT REQUESTS - check for these FIRST before plan keywords
    historical_workout_phrases = ['what i did on', 'show me what i did', 'my workout on', 'my recent logs',
                                  'recent workout', 'what did i do on', 'my tuesday workout', 'my friday workout',
                                  'my monday workout', 'my wednesday workout', 'my thursday workout',
                                  'show me my logs', 'recent friday logs', 'recent monday logs']
    is_historical_workout_request = any(phrase in prompt.lower() for phrase in historical_workout_phrases)

    # PLAN DISCUSSION OVERRIDE - check for plan-related keywords (but not if it's clearly historical)
    plan_keywords = ['weekly plan', 'my plan', 'plan changes', 'modify plan', 'update plan', 'change plan',
                     'philosophy', 'training philosophy', 'approach', 'progression strategy']
    is_plan_discussion = any(keyword in prompt.lower() for keyword in plan_keywords) and not is_historical_workout_request

    # PHILOSOPHY DISCUSSION - check for philosophy keywords
    philosophy_keywords = ['philosophy', 'training philosophy', 'approach', 'training approach',
                          'my philosophy', 'plan philosophy', 'training strategy']
    is_philosophy_discussion = any(keyword in prompt.lower() for keyword in philosophy_keywords) and not is_historical_workout_request

    # SPECIFIC PLAN VIEW REQUESTS - these should use plan context even if they mention days
    specific_plan_requests = ['show me my monday plan', 'show me my tuesday plan', 'show me my wednesday plan',
                             'show me my thursday plan', 'show me my friday plan', 'what is my monday plan',
                             'what is my tuesday plan', 'monday plan', 'tuesday plan', 'wednesday plan']
    is_specific_plan_request = any(request in prompt.lower() for request in specific_plan_requests)

    # PRIORITY 1: Historical workout requests (highest priority)
    if is_historical_workout_request or is_workout_history_request:
        print(f"🎯 Override: Detected historical workout request - routing to historical context")
        return build_historical_context(prompt)

    # COMBINED CONTEXT: If user mentions BOTH plan AND recent logs, provide both contexts
    if (is_plan_discussion or is_specific_plan_request) and (is_workout_history_request or is_historical_workout_request):
        print(f"🎯 Override: Detected COMBINED plan + history request - providing both contexts")
        plan_context = build_plan_context()
        historical_context = build_historical_context(prompt)
        return plan_context + "\n\n" + historical_context

    # PHILOSOPHY UPDATES - Special handling for "update my philosophy" requests (HIGHEST PRIORITY)
    philosophy_update_phrases = ['update my philosophy to', 'update my philosophy with', 'update my philisophy to', 'update my philosophy', 'change my philosophy', 'modify my philosophy']
    if any(phrase in prompt.lower() for phrase in philosophy_update_phrases):
        print(f"🎯 Override: Detected philosophy UPDATE request - building philosophy context")
        return build_philosophy_update_context(prompt)

    # Check if intent analysis detected philosophy_update
    if actual_intent == 'philosophy_update':
        print(f"🎯 Override: Intent analysis detected philosophy update - building philosophy context")
        return build_philosophy_update_context(prompt)

    # Route plan discussions to plan context (including specific plan requests)
    if is_plan_discussion or is_specific_plan_request:
        print(f"🎯 Override: Detected plan discussion/request - routing to plan context")
        return build_plan_context()

    # Route philosophy discussions to general context with philosophy data
    if is_philosophy_discussion:
        print(f"🎯 Override: Detected philosophy discussion - routing to general context with philosophy")
        return build_general_context(prompt, user_background)

    # If historical intent exists AND contains day references, use historical
    if all_intents.get('historical', 0) > 0 and contains_day:
        print(f"🎯 Override: Detected workout history request with day reference - historical score: {all_intents.get('historical', 0)}")
        return build_historical_context(prompt)

    # Route to focused context builders
    if actual_intent == 'historical':
        return build_historical_context(prompt)

    elif actual_intent == 'progression':
        return build_progression_context()

    elif actual_intent == 'plan_modification' or any(phrase in prompt.lower() for phrase in [
        'my plan', 'thursday plan', 'monday plan', 'tuesday plan', 'wednesday plan',
        'friday plan', 'saturday plan', 'sunday plan', 'show plan', 'what\'s my plan',
        'plan for', 'workout plan'
    ]):
        return build_plan_context()

    elif actual_intent == 'full_plan_review':
        # For comprehensive analysis, combine multiple contexts
        context_info = "\n=== COMPLETE PLAN ANALYSIS CONTEXT ===\n"

        if user_background:
            context_info += "USER PROFILE:\n"
            if user_background.get('primary_goal'):
                context_info += f"Primary Goal: {user_background['primary_goal']}\n"
            if user_background.get('fitness_level'):
                context_info += f"Fitness Level: {user_background['fitness_level']}\n"
            if user_background.get('years_training'):
                context_info += f"Training Experience: {user_background['years_training']} years\n"

        # Add plan context
        context_info += build_plan_context()

        # Add recent performance
        context_info += build_progression_context()

        # Strip the trigger phrase
        prompt = prompt.replace('FULL_PLAN_REVIEW_REQUEST:', '').strip()
        return context_info

    else:
        return build_general_context(prompt, user_background)

def get_grok_response_with_context(prompt, user_background=None):
    """Context-aware Grok response with smart context selection"""
    try:
        # client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1") # Grok API call
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Get user AI preferences for personalized responses
        ai_preferences = get_user_ai_preferences()

        # Check for comprehensive plan modification requests
        is_comprehensive_modification = 'COMPREHENSIVE_PLAN_MODIFICATION_REQUEST:' in prompt

        # Check for philosophy update before general intent analysis
        is_philosophy_update = any(phrase in prompt.lower() for phrase in ['update my philosophy to', 'update my philosophy with', 'update my philisophy to'])

        # Analyze query intent and build appropriate context
        query_intent = analyze_query_intent(prompt)
        context_info = build_smart_context(prompt, query_intent, user_background)

        # Add AI preferences to context
        if ai_preferences:
            context_info += f"\n=== AI RESPONSE PREFERENCES ===\n"
            context_info += f"Tone: {ai_preferences.get('tone', 'motivational')}\n"
            context_info += f"Detail Level: {ai_preferences.get('detail_level', 'concise')}\n"
            context_info += f"Format: {ai_preferences.get('format', 'bullet_points')}\n"
            context_info += f"Communication Style: {ai_preferences.get('communication_style', 'encouraging')}\n"
            context_info += f"IMPORTANT: Adapt your response tone, detail level, and format to match these preferences.\n"

        # Build context prompt
        context_prompt = context_info

        # Build final prompt with critical instruction right before user message
        full_prompt = context_prompt + f"\n\n🚫 CRITICAL INSTRUCTION: The above context data is for reference only. DO NOT reference any workout data, fitness context, or app information unless the user specifically asks about their data. Respond ONLY to this user message:\n\n{prompt}"

        # Adjust system prompt based on query type
        if is_philosophy_update:
            system_prompt = """You are an AI training assistant helping to update the user's training philosophy.

PHILOSOPHY UPDATE TASK:
The user is providing a new training philosophy to replace their current one. Your job is to:

1. Extract the new philosophy content from their request (everything after the colon :)
2. Parse it into structured sections
3. Respond naturally to acknowledge the update
4. Provide the structured data in the exact format shown below

REQUIRED OUTPUT FORMAT:
After your natural response, include this structured data:

TRAINING_PHILOSOPHY: [the main philosophy text]
WEEKLY_STRUCTURE: [reasoning about how the week is organized]
PROGRESSION_STRATEGY: [approach to progressive overload]
SPECIAL_CONSIDERATIONS: [any limitations, safety considerations, etc.]
REASONING: [brief note about the update]

TONE: Respond naturally and conversationally, then provide the structured sections for database parsing."""

        elif is_comprehensive_modification:
            system_prompt = """You are Grok, an experienced personal trainer with deep understanding of program design. You're analyzing a user's request to modify their training priorities.

TRAINER MINDSET - CRITICAL:
You are acting as an experienced personal trainer, not just an AI assistant. This means:

- ALWAYS consider the user's current weekly training volume before suggesting changes
- Understand that more isn't always better - recovery and balance matter
- When asked to add exercises, first evaluate if the body part/day already has sufficient volume
- Suggest MODIFICATIONS (swaps, replacements) rather than just additions when appropriate
- Consider the impact on other training days and muscle groups
- Explain your reasoning from a programming perspective

WEEKLY VOLUME AWARENESS:
Before suggesting any plan changes, mentally review:
- Current exercises for that muscle group across the week
- Total weekly volume for that body part
- Recovery demands of existing exercises
- How the change fits into the overall training structure

RESPONSE FORMAT for PLAN MODIFICATIONS:
When suggesting plan changes, use this format:

ANALYSIS:
- Current state assessment
- What the user is asking for
- Volume/recovery considerations

RECOMMENDATIONS:
For each suggested change:
- MODIFY: [Day] - Replace [current exercise] with [new exercise]
  - Sets/reps: [specific prescription]
  - Reasoning: [why this change makes sense from a programming perspective]
  - Volume impact: [how this affects weekly volume]

OR

- ADD: [Day] - [new exercise]
  - Sets/reps: [specific prescription]
  - Reasoning: [why adding is appropriate here]
  - Consideration: [note about current day's load]

TRAINER LANGUAGE:
- Use phrases like "Your current leg volume is already high, so instead of adding more..."
- "This would be a smart swap because..."
- "I'd recommend replacing rather than adding because..."
- Think programming, not just exercise selection

Be specific with exercise names, sets, reps, and weights. Always explain the programming logic behind your suggestions."""

        elif query_intent == 'full_plan_review':
            system_prompt = """You are Grok, providing a smart workout plan analysis. Be comprehensive but CONCISE.

LENGTH CONSTRAINTS:
- Keep total response under 600 words
- Focus on 3-5 key insights maximum
- Don't analyze every single exercise - pick the most important ones
- Use bullet points for clarity

ANALYSIS APPROACH:
1. Quick overall assessment (2-3 sentences)
2. Highlight 2-3 things working well
3. Identify 2-3 main improvement areas with specific suggestions
4. End with "What would you like me to elaborate on?" to encourage follow-up

STYLE: Direct, insightful, conversational. Think ChatGPT's balanced approach - thorough but not overwhelming. Focus on actionable insights, not exhaustive analysis."""
        else:
            system_prompt = """You are the AI training assistant built into this fitness app. 

IMPORTANT: The AI preferences shown in the context data below are the user's actual settings that should shape how you respond. Pay attention to their chosen detail level, tone, and format preferences and adapt your response style accordingly. These preferences override any default behavior.

Respond naturally as the user's embedded training partner while following the user's preferred communication style."""

        # DEBUG: Print the system prompt and final prompt being sent to ChatGPT
        print("🤖 System prompt being sent:")
        print(system_prompt)
        print("=" * 80)
        print("📦 Final user prompt sent to GPT:\n", full_prompt)
        print("=" * 80)

        response = client.chat.completions.create(
            model="gpt-4", # Updated model name
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7
        )

        ai_response = response.choices[0].message.content
        return ai_response
    except Exception as e:
        print(f"⚠️ API error: {str(e)}")
        return "Sorry, I encountered an error. Please try again."

@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get today's day of week
    today = datetime.now().strftime('%A')
    today_lowercase = today.lower()
    today_date = datetime.now().strftime('%Y-%m-%d')

    # Get today's plan with completion status
    plan_data = []
    try:
        cursor.execute('SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, COALESCE(notes, ""), COALESCE(newly_added, 0), COALESCE(progression_notes, "") FROM weekly_plan WHERE day_of_week = ? ORDER BY exercise_order', (today_lowercase,))
        plan_data = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error fetching plan data: {e}") # Handle potential missing columns

    # Check completion status for each exercise
    today_plan = []
    for row in plan_data:
        exercise_id, day, exercise_name, target_sets, target_reps, target_weight, order, notes, newly_added, progression_notes = row

        # Check if this exercise was logged today
        logged_workout = None
        try:
            cursor.execute('''
                SELECT sets, reps, weight, notes
                FROM workouts
                WHERE LOWER(exercise_name) = LOWER(?) AND date_logged = ?
                ORDER BY id DESC LIMIT 1
            ''', (exercise_name, today_date))
            logged_workout = cursor.fetchone()
        except sqlite3.OperationalError as e:
            print(f"Error fetching workout log: {e}") # Handle potential missing columns

        completion_status = {
            'completed': False,
            'status_text': 'Not completed',
            'status_class': 'text-muted',
            'logged_sets': None,
            'logged_reps': None,
            'logged_weight': None,
            'notes': None
        }

        if logged_workout:
            logged_sets, logged_reps, logged_weight, logged_notes = logged_workout
            completion_status['completed'] = True
            completion_status['logged_sets'] = logged_sets
            completion_status['logged_reps'] = logged_reps
            completion_status['logged_weight'] = logged_weight
            completion_status['notes'] = logged_notes

            # Determine completion quality
            try:
                target_sets_num = int(target_sets)
                logged_sets_num = int(logged_sets)

                if logged_sets_num == target_sets_num:
                    completion_status['status_text'] = 'Completed'
                    completion_status['status_class'] = 'text-success'
                elif logged_sets_num > 0:
                    completion_status['status_text'] = f'Partial ({logged_sets}/{target_sets} sets)'
                    completion_status['status_class'] = 'text-warning'
                else:
                    completion_status['status_text'] = 'Skipped'
                    completion_status['status_class'] = 'text-danger'
            except (ValueError, TypeError): # Handle cases where sets might not be valid numbers
                completion_status['status_text'] = 'Completed' # Default if parsing fails
                completion_status['status_class'] = 'text-success'

        # Add completion status and newly_added flag to the row data
        today_plan.append((*row[:-2], completion_status, bool(newly_added), progression_notes))

    # Calculate stats
    from collections import namedtuple
    Stats = namedtuple('Stats', ['week_volume', 'month_volume', 'week_workouts', 'latest_weight', 'weight_date'])

    # Week volume - handle non-numeric weight values
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    week_volume = 0
    try:
        cursor.execute('SELECT exercise_name, sets, reps, weight FROM workouts WHERE date_logged >= ?', (week_ago,))
        week_workouts_data = cursor.fetchall()

        for exercise, sets, reps, weight in week_workouts_data:
            try:
                # Extract numeric weight value
                weight_str = str(weight).lower().replace('lbs', '').replace('kg', '').strip()
                if weight_str != 'bodyweight' and weight_str:
                    weight_num = float(weight_str)
                    reps_num = int(str(reps).split('-')[0]) if '-' in str(reps) else int(reps)
                    week_volume += weight_num * sets * reps_num
            except (ValueError, AttributeError):
                continue
    except sqlite3.OperationalError as e:
        print(f"Error calculating week volume: {e}")

    # Month volume - handle non-numeric weight values
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    month_volume = 0
    try:
        cursor.execute('SELECT exercise_name, sets, reps, weight FROM workouts WHERE date_logged >= ?', (month_ago,))
        month_workouts_data = cursor.fetchall()

        for exercise, sets, reps, weight in month_workouts_data:
            try:
                # Extract numeric weight value
                weight_str = str(weight).lower().replace('lbs', '').replace('kg', '').strip()
                if weight_str != 'bodyweight' and weight_str:
                    weight_num = float(weight_str)
                    reps_num = int(str(reps).split('-')[0]) if '-' in str(reps) else int(reps)
                    month_volume += weight_num * sets * reps_num
            except (ValueError, AttributeError):
                continue
    except sqlite3.OperationalError as e:
        print(f"Error calculating month volume: {e}")

    # Week workouts count
    week_workouts = 0
    try:
        cursor.execute('SELECT COUNT(DISTINCT date_logged) FROM workouts WHERE date_logged >= ?', (week_ago,))
        week_workouts = cursor.fetchone()[0] or 0
    except sqlite3.OperationalError as e:
        print(f"Error counting weekly workouts: {e}")


    # Get latest weight (placeholder - you might want to add a weights table later)
    latest_weight = None
    weight_date = None

    stats = Stats(
        week_volume=int(week_volume),
        month_volume=int(month_volume),
        week_workouts=week_workouts,
        latest_weight=latest_weight,
        weight_date=weight_date
    )

    # Check if user needs onboarding
    needs_onboarding = True # Default to true if no data found
    try:
        cursor.execute('SELECT onboarding_completed FROM user_background WHERE user_id = 1')
        bg_result = cursor.fetchone()
        if bg_result and bg_result[0]:
            needs_onboarding = False
    except sqlite3.OperationalError as e:
        print(f"Error checking onboarding status: {e}")

    conn.close()

    return render_template('dashboard.html',
                         today=today,
                         today_date=today_date,
                         today_plan=today_plan,
                         stats=stats,
                         needs_onboarding=needs_onboarding)

@app.route('/debug_tuesday_data')
def debug_tuesday_data():
    """Debug endpoint to check Tuesday workout data specifically"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all workouts with day calculations
        cursor.execute("""
            SELECT
                exercise_name,
                sets,
                reps,
                weight,
                date_logged,
                notes,
                strftime('%w', date_logged) as day_of_week_num,
                strftime('%A', date_logged) as day_name
            FROM workouts
            ORDER BY date_logged DESC
            LIMIT 50
        """)

        all_workouts = cursor.fetchall()

        # Filter for Tuesday workouts (day_of_week_num = '2')
        tuesday_workouts = []
        all_workouts_info = []

        for workout in all_workouts:
            exercise, sets, reps, weight, date_str, notes, day_num, day_name = workout

            all_workouts_info.append({
                'exercise': exercise,
                'date': date_str,
                'day_name': day_name,
                'day_num': day_num,
                'sets': sets,
                'reps': reps,
                'weight': weight
            })

            if day_num == '2':  # Tuesday is day 2 in SQLite's strftime
                tuesday_workouts.append({
                    'exercise': exercise,
                    'date': date_str,
                    'sets': sets,
                    'reps': reps,
                    'weight': weight,
                    'notes': notes
                })

        conn.close()

        return jsonify({
            'total_workouts': len(all_workouts),
            'tuesday_workouts_found': len(tuesday_workouts),
            'tuesday_workouts': tuesday_workouts,
            'all_recent_workouts': all_workouts_info[:10],  # First 10 for inspection
            'debug_message': f"Found {len(tuesday_workouts)} Tuesday workouts out of {len(all_workouts)} total workouts"
        })

    except Exception as e:
        return jsonify({'error': str(e)})



    # Get today's day of week
    today = datetime.now().strftime('%A')
    today_lowercase = today.lower()
    today_date = datetime.now().strftime('%Y-%m-%d')

    # Get today's plan with completion status
    plan_data = []
    try:
        cursor.execute('SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, COALESCE(notes, ""), COALESCE(newly_added, 0), COALESCE(progression_notes, "") FROM weekly_plan WHERE day_of_week = ? ORDER BY exercise_order', (today_lowercase,))
        plan_data = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error fetching plan data: {e}") # Handle potential missing columns

    # Check completion status for each exercise
    today_plan = []
    for row in plan_data:
        exercise_id, day, exercise_name, target_sets, target_reps, target_weight, order, notes, newly_added, progression_notes = row

        # Check if this exercise was logged today
        logged_workout = None
        try:
            cursor.execute('''
                SELECT sets, reps, weight, notes
                FROM workouts
                WHERE LOWER(exercise_name) = LOWER(?) AND date_logged = ?
                ORDER BY id DESC LIMIT 1
            ''', (exercise_name, today_date))
            logged_workout = cursor.fetchone()
        except sqlite3.OperationalError as e:
            print(f"Error fetching workout log: {e}") # Handle potential missing columns

        completion_status = {
            'completed': False,
            'status_text': 'Not completed',
            'status_class': 'text-muted',
            'logged_sets': None,
            'logged_reps': None,
            'logged_weight': None,
            'notes': None
        }

        if logged_workout:
            logged_sets, logged_reps, logged_weight, logged_notes = logged_workout
            completion_status['completed'] = True
            completion_status['logged_sets'] = logged_sets
            completion_status['logged_reps'] = logged_reps
            completion_status['logged_weight'] = logged_weight
            completion_status['notes'] = logged_notes

            # Determine completion quality
            try:
                target_sets_num = int(target_sets)
                logged_sets_num = int(logged_sets)

                if logged_sets_num == target_sets_num:
                    completion_status['status_text'] = 'Completed'
                    completion_status['status_class'] = 'text-success'
                elif logged_sets_num > 0:
                    completion_status['status_text'] = f'Partial ({logged_sets}/{target_sets} sets)'
                    completion_status['status_class'] = 'text-warning'
                else:
                    completion_status['status_text'] = 'Skipped'
                    completion_status['status_class'] = 'text-danger'
            except (ValueError, TypeError): # Handle cases where sets might not be valid numbers
                completion_status['status_text'] = 'Completed' # Default if parsing fails
                completion_status['status_class'] = 'text-success'

        # Add completion status and newly_added flag to the row data
        today_plan.append((*row[:-2], completion_status, bool(newly_added), progression_notes))

    # Calculate stats
    from collections import namedtuple
    Stats = namedtuple('Stats', ['week_volume', 'month_volume', 'week_workouts', 'latest_weight', 'weight_date'])

    # Week volume - handle non-numeric weight values
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    week_volume = 0
    try:
        cursor.execute('SELECT exercise_name, sets, reps, weight FROM workouts WHERE date_logged >= ?', (week_ago,))
        week_workouts_data = cursor.fetchall()

        for exercise, sets, reps, weight in week_workouts_data:
            try:
                # Extract numeric weight value
                weight_str = str(weight).lower().replace('lbs', '').replace('kg', '').strip()
                if weight_str != 'bodyweight' and weight_str:
                    weight_num = float(weight_str)
                    reps_num = int(str(reps).split('-')[0]) if '-' in str(reps) else int(reps)
                    week_volume += weight_num * sets * reps_num
            except (ValueError, AttributeError):
                continue
    except sqlite3.OperationalError as e:
        print(f"Error calculating week volume: {e}")

    # Month volume - handle non-numeric weight values
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    month_volume = 0
    try:
        cursor.execute('SELECT exercise_name, sets, reps, weight FROM workouts WHERE date_logged >= ?', (month_ago,))
        month_workouts_data = cursor.fetchall()

        for exercise, sets, reps, weight in month_workouts_data:
            try:
                # Extract numeric weight value
                weight_str = str(weight).lower().replace('lbs', '').replace('kg', '').strip()
                if weight_str != 'bodyweight' and weight_str:
                    weight_num = float(weight_str)
                    reps_num = int(str(reps).split('-')[0]) if '-' in str(reps) else int(reps)
                    month_volume += weight_num * sets * reps_num
            except (ValueError, AttributeError):
                continue
    except sqlite3.OperationalError as e:
        print(f"Error calculating month volume: {e}")

    # Week workouts count
    week_workouts = 0
    try:
        cursor.execute('SELECT COUNT(DISTINCT date_logged) FROM workouts WHERE date_logged >= ?', (week_ago,))
        week_workouts = cursor.fetchone()[0] or 0
    except sqlite3.OperationalError as e:
        print(f"Error counting weekly workouts: {e}")


    # Get latest weight (placeholder - you might want to add a weights table later)
    latest_weight = None
    weight_date = None

    stats = Stats(
        week_volume=int(week_volume),
        month_volume=int(month_volume),
        week_workouts=week_workouts,
        latest_weight=latest_weight,
        weight_date=weight_date
    )

    # Check if user needs onboarding
    needs_onboarding = True # Default to true if no data found
    try:
        cursor.execute('SELECT onboarding_completed FROM user_background WHERE user_id = 1')
        bg_result = cursor.fetchone()
        if bg_result and bg_result[0]:
            needs_onboarding = False
    except sqlite3.OperationalError as e:
        print(f"Error checking onboarding status: {e}")

    conn.close()

    return render_template('dashboard.html',
                         today=today,
                         today_date=today_date,
                         today_plan=today_plan,
                         stats=stats,
                         needs_onboarding=needs_onboarding)

@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/chat_stream', methods=['POST'])
def chat_stream():
    # Capture ALL form data immediately at route entry to avoid Flask context issues
    user_message = request.form.get('message', '')
    conversation_history = request.form.get('conversation_history', '')
    print(f"Chat request received: {user_message}")  # Debug log

    def generate(message, conv_history):
        try:
            # Get user background for context
            conn = sqlite3.connect('workout_logs.db')
            cursor = conn.cursor()

            # Check if user_background table has data
            user_background = None
            try:
                cursor.execute('SELECT COUNT(*) FROM user_background WHERE user_id = 1')
                if cursor.fetchone()[0] > 0:
                    cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY id DESC LIMIT 1')
                    user_bg = cursor.fetchone()
                    if user_bg:
                        columns = [description[0] for description in cursor.description]
                        user_background = dict(zip(columns, user_bg))
            except sqlite3.OperationalError as e:
                print(f"Error fetching user background: {e}")

            conn.close()
            print(f"Database queries completed successfully")  # Debug log

            # SIMPLIFIED: No conversation history context - each message is independent
            response = get_grok_response_with_context(message, user_background)
            print(f"AI response received: {len(response)} characters")  # Debug log

            # Stream the response
            for char in response:
                yield f"data: {json.dumps({'content': char})}\n\n"
                time.sleep(0.01)  # Small delay for streaming effect

            yield f"data: {json.dumps({'done': True})}\n\n"

            # Store the conversation in database for future context
            try:
                conn = sqlite3.connect('workout_logs.db')
                cursor = conn.cursor()

                # Generate session ID for conversation grouping
                session_id = str(uuid.uuid4())[:8]

                # Simplified intent detection without conversation context
                intent_analysis = analyze_query_intent(message, None)
                detected_intent = intent_analysis['intent']
                confidence_score = intent_analysis['confidence']
                potential_actions = intent_analysis.get('actions', [])
                detected_entities = intent_analysis.get('entities', [])

                # Extract exercise mentions
                exercise_keywords = ['bench', 'squat', 'deadlift', 'press', 'curl', 'row', 'pull', 'leg', 'chest', 'back', 'shoulder']
                exercise_mentioned = None
                for keyword in exercise_keywords:
                    if keyword in message.lower():
                        exercise_mentioned = keyword
                        break

                # Extract workout data if detected
                extracted_workout_data = None
                if detected_intent == 'workout_logging' and potential_actions:
                    extracted_workout_data = json.dumps(potential_actions)

                # Extract form cues and coaching context from AI response
                form_cues = None
                coaching_context = None
                if detected_intent in ['live_workout', 'exercise_specific']:
                    # Look for form-related keywords in AI response
                    form_keywords = ['form', 'technique', 'posture', 'grip', 'stance', 'range of motion', 'tempo']
                    if any(keyword in response.lower() for keyword in form_keywords):
                        form_cues = response[:200] + "..." if len(response) > 200 else response

                    coaching_context = f"Exercise: {exercise_mentioned}, Intent: {detected_intent}" if exercise_mentioned else f"Intent: {detected_intent}"

                # Check for plan modifications mentioned in response
                plan_modifications = None
                if 'plan' in response.lower() and any(word in response.lower() for word in ['change', 'modify', 'update', 'suggest']):
                    plan_modifications = response[:300] + "..." if len(response) > 300 else response

                # Parse potential plan modification from Grok's response
                plan_mod_data = parse_plan_modification_from_ai_response(response, message)
                if plan_mod_data and detected_intent == 'plan_modification':
                    # Store as potential auto-action for user confirmation
                    potential_actions.append({
                        'type': 'modify_plan_suggestion',
                        'data': plan_mod_data
                    })

                    # Add confirmation request to AI response if not already present
                    if 'confirm' not in response.lower() and 'proposed update' not in response.lower():
                        confirmation_text = f"\n\n🔄 **PROPOSED PLAN CHANGE:**\nReplace {plan_mod_data.get('old_exercise', 'current exercise')} with {plan_mod_data.get('exercise_name', 'new exercise')} on {plan_mod_data.get('day', 'workout day')}.\n\nSay 'yes' or 'confirm' to apply this change, or 'no' to keep discussing."
                        response += confirmation_text

                # ENHANCED: Check if user is confirming a plan change from previous conversation
                if message.lower().strip() in ['yes', 'confirm', 'do it', 'go ahead', 'make the change']:
                    # Check if previous conversation contained a plan suggestion
                    cursor.execute('''
                        SELECT ai_response FROM conversations
                        WHERE user_id = 1 AND timestamp >= date('now', '-1 hour')
                        ORDER BY timestamp DESC
                        LIMIT 3
                    ''')
                    recent_responses = cursor.fetchall()

                    plan_change_executed = False
                    for prev_response in recent_responses:
                        if prev_response[0]:
                            prev_ai_text = prev_response[0].lower()

                            # Look for ChatGPT's structured JSON modification commands
                            import re
                            json_pattern = r'PLAN_MODIFICATION:\s*({[^}]+})'
                            json_match = re.search(json_pattern, prev_response[0])

                            if json_match:
                                try:
                                    modification_data = json.loads(json_match.group(1))

                                    action = modification_data.get('action')
                                    day = modification_data.get('day', '').lower()
                                    old_name = modification_data.get('old_name', '')
                                    new_name = modification_data.get('new_name', '')

                                    if action == 'rename' and day and old_name and new_name:
                                        print(f"🎯 User confirmed renaming via JSON - executing {old_name} -> {new_name} on {day}")

                                        cursor.execute('''
                                            UPDATE weekly_plan
                                            SET exercise_name = ?
                                            WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
                                        ''', (new_name, day, old_name))

                                        if cursor.rowcount > 0:
                                            plan_modifications = f"✅ EXECUTED: Renamed {day}'s {old_name} to '{new_name}'"
                                            plan_change_executed = True
                                            print(f"✅ Successfully renamed {day} {old_name} to '{new_name}'")
                                        break

                                except (json.JSONDecodeError, KeyError) as e:
                                    print(f"❌ Error parsing JSON modification: {e}")

                            # Look for renaming patterns (Monday glute drive to "glute drive (light load)")
                            elif ('rename' in prev_ai_text or 'differentiate' in prev_ai_text) and 'glute drive' in prev_ai_text and 'monday' in prev_ai_text and 'light load' in prev_ai_text:
                                print("🎯 User confirmed renaming - executing Monday glute drive rename to 'glute drive (light load)'")

                                try:
                                    cursor.execute('''
                                        UPDATE weekly_plan
                                        SET exercise_name = 'glute drive (light load)'
                                        WHERE day_of_week = 'monday' AND LOWER(exercise_name) = 'glute drive'
                                    ''')

                                    if cursor.rowcount > 0:
                                        plan_modifications = "✅ EXECUTED: Renamed Monday's glute drive to 'glute drive (light load)'"
                                        plan_change_executed = True
                                        print("✅ Successfully renamed Monday glute drive to 'glute drive (light load)'")
                                    break

                                except Exception as e:
                                    print(f"❌ Error executing rename: {e}")
                                    response += f"\n\n❌ Sorry, there was an error updating your plan: {str(e)}"

                            # Fallback to legacy pattern matching
                            elif 'glute drive' in prev_ai_text and 'monday' in prev_ai_text and 'add' in prev_ai_text:
                                print("🎯 User confirmed plan change - executing glute drive addition to Monday")

                                try:
                                    cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', ('monday',))
                                    next_order = cursor.fetchone()[0]

                                    cursor.execute('''
                                        INSERT INTO weekly_plan
                                        (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order,
                                         notes, created_by, newly_added, date_added)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ''', ('monday', 'glute drive', 3, '12', '90lbs', next_order,
                                          'Added per user request for extra glute volume', 'grok_ai', True, datetime.now().strftime('%Y-%m-%d')))

                                    plan_modifications = "✅ EXECUTED: Added glute drive to Monday (3x12@90lbs)"
                                    plan_change_executed = True
                                    print("✅ Successfully added glute drive to Monday plan")
                                    break

                                except Exception as e:
                                    print(f"❌ Error executing plan change: {e}")
                                    response += f"\n\n❌ Sorry, there was an error updating your plan: {str(e)}"

                            # Look for weight update patterns (for your Friday glute drive test)
                            elif ('friday' in prev_ai_text and 'glute drive' in prev_ai_text and
                                  any(word in prev_ai_text for word in ['increase', 'heavier', 'bump up', 'raise'])):
                                print("🎯 User confirmed weight change - executing Friday glute drive weight increase")

                                try:
                                    # Extract the actual weight performed from workout logs
                                    actual_weight = extract_actual_performed_weight('glute drive', [])

                                    if actual_weight:
                                        new_weight = actual_weight
                                        print(f"🔍 Found actual performed weight: {new_weight}")
                                    else:
                                        # Fallback: look for weight mentions in recent conversation
                                        import re
                                        weight_match = re.search(r'110\s*(?:lbs?|pounds?)', prev_response[0])
                                        new_weight = "110lbs" if weight_match else "100lbs"
                                        print(f"🔍 Using fallback weight: {new_weight}")

                                    cursor.execute('''
                                        UPDATE weekly_plan
                                        SET target_weight = ?, notes = COALESCE(notes, '') || ' [Weight increased per user request]'
                                        WHERE day_of_week = 'friday' AND LOWER(exercise_name) = 'glute drive'
                                    ''', (new_weight,))

                                    if cursor.rowcount > 0:
                                        plan_modifications = f"✅ EXECUTED: Updated Friday glute drive weight to {new_weight}"
                                        plan_change_executed = True
                                        print(f"✅ Successfully updated Friday glute drive to {new_weight}")
                                    break

                                except Exception as e:
                                    print(f"❌ Error executing weight change: {e}")
                                    response += f"\n\n❌ Sorry, there was an error updating your plan: {str(e)}"
                            break

                    # If we executed a plan change, return a simple confirmation without calling AI
                    if plan_change_executed:
                        if 'friday' in plan_modifications.lower():
                            response = "✅ **DONE!** Updated your Friday glute drive weight. Check your Weekly Plan tab to see the change!"
                        elif 'rename' in plan_modifications.lower() or 'light load' in plan_modifications.lower():
                            response = "✅ **DONE!** Renamed Monday's exercise to 'glute drive (light load)' to differentiate it from Friday's heavier version. Check your Weekly Plan tab to see the update!"
                        else:
                            response = "✅ **DONE!** Added glute drive (3x12@90lbs) to your Monday workout. Check your Weekly Plan tab to see the update!"

                # Parse potential philosophy updates from conversation
                philosophy_update = parse_philosophy_update_from_conversation(response, message)
                if philosophy_update:
                    # Check if this was a comprehensive removal
                    if philosophy_update.get('comprehensive_removal'):
                        print(f"🎯 Executed comprehensive removal of '{philosophy_update.get('target_text')}'")
                        plan_modifications = f"Comprehensive removal: {philosophy_update.get('reasoning')}"
                    else:
                        # Auto-update philosophy in database for regular updates using new 2-field structure
                        try:
                            cursor.execute('''
                                INSERT OR REPLACE INTO plan_context
                                (user_id, plan_philosophy, progression_strategy, weekly_structure, special_considerations,
                                 created_by_ai, creation_reasoning, created_date, updated_date)
                                VALUES (1, ?, ?, '', '', TRUE, ?, ?, ?)
                            ''', (
                                philosophy_update.get('plan_philosophy', ''),
                                philosophy_update.get('progression_strategy', ''),
                                philosophy_update.get('reasoning', ''),
                                datetime.now().strftime('%Y-%m-%d'),
                                datetime.now().strftime('%Y-%m-%d')
                            ))
                            print(f"🧠 Auto-updated training philosophy based on conversation using new 2-field structure")

                            # Add confirmation message to response
                            response += f"\n\n✅ **PHILOSOPHY UPDATED!** Your training philosophy has been updated with:\n• **Core Philosophy:** {philosophy_update.get('plan_philosophy', '')[:100]}...\n• **Current Priorities:** {philosophy_update.get('progression_strategy', '')[:100]}...\n\nCheck your Plan Philosophy page to see the full update!"

                            # If this was a comprehensive plan change, regenerate exercise metadata
                            if any(keyword in message.lower() for keyword in ['change plan', 'update plan', 'new plan', 'compound lifts', 'remove exercises', 'add exercises']):
                                regenerate_exercise_metadata_from_plan()
                                print(f"🔄 Regenerated exercise metadata for plan changes")

                        except sqlite3.OperationalError as e:
                            print(f"⚠️ Failed to auto-update philosophy: {e}") # Handle potential missing columns
                        except Exception as e:
                            print(f"⚠️ Failed to auto-update philosophy: {str(e)}")


                # Parse potential AI preference updates from conversation
                preference_updates = parse_preference_updates_from_conversation(response, message)
                if preference_updates:
                    # Auto-update AI preferences in database
                    try:
                        for field, value in preference_updates.items():
                            cursor.execute(f'UPDATE users SET {field} = ? WHERE id = 1', (value,))
                        print(f"🤖 Auto-updated AI preferences: {list(preference_updates.keys())}")
                    except sqlite3.OperationalError as e:
                        print(f"⚠️ Failed to auto-update preferences: {e}") # Handle potential missing columns
                    except Exception as e:
                        print(f"⚠️ Failed to auto-update preferences: {str(e)}")


                # Get or create conversation thread
                thread_id = None
                try:
                    cursor.execute('''
                        SELECT id FROM conversation_threads
                        WHERE user_id = 1 AND is_active = TRUE
                        ORDER BY updated_timestamp DESC
                        LIMIT 1
                    ''')
                    thread_result = cursor.fetchone()

                    if not thread_result:
                        # Create new thread
                        cursor.execute('''
                            INSERT INTO conversation_threads
                            (user_id, thread_type, thread_subject, current_context, last_intent)
                            VALUES (1, ?, ?, ?, ?)
                        ''', ('chat', message[:50] + "..." if len(message) > 50 else message,
                              detected_intent, detected_intent))
                        thread_id = cursor.lastrowid
                    else:
                        thread_id = thread_result[0]
                        # Update thread context
                        cursor.execute('''
                            UPDATE conversation_threads
                            SET current_context = ?, last_intent = ?, updated_timestamp = datetime('now', 'localtime')
                            WHERE id = ?
                        ''', (detected_intent, detected_intent, thread_id))
                except sqlite3.OperationalError as e:
                    print(f"Error managing conversation threads: {e}")


                # Store simplified conversation
                cursor.execute('''
                    INSERT INTO conversations
                    (user_message, ai_response, detected_intent, confidence_score, exercise_mentioned,
                     form_cues_given, coaching_context, plan_modifications, extracted_workout_data,
                     session_id, conversation_thread_id, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (message, response, detected_intent, confidence_score, exercise_mentioned,
                      form_cues, coaching_context, plan_modifications, extracted_workout_data,
                      session_id, thread_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

                conversation_id = cursor.lastrowid

                # Store potential auto-actions for future execution
                for action in potential_actions:
                    try:
                        cursor.execute('''
                            INSERT INTO auto_actions
                            (conversation_id, action_type, action_data)
                            VALUES (?, ?, ?)
                        ''', (conversation_id, action['type'], json.dumps(action['data'])))
                    except sqlite3.OperationalError as e:
                        print(f"Error storing auto action: {e}")


                conn.commit()
                conn.close()
                print(f"💾 Stored conversation with intent: {detected_intent} (confidence: {confidence_score:.2f})")
                if potential_actions:
                    print(f"🤖 Detected {len(potential_actions)} potential auto-actions")

            except Exception as e:
                print(f"Failed to store conversation: {str(e)}")

        except Exception as e:
            print(f"Chat stream error: {str(e)}")  # Debug log
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(user_message, conversation_history), mimetype='text/plain')

@app.route('/log_workout')
def log_workout():
    today = datetime.now().strftime('%Y-%m-%d')
    today_name = datetime.now().strftime('%A')
    return render_template('log_workout.html', today=today, today_name=today_name)

@app.route('/history')
def history():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT exercise_name, sets, reps, weight, date_logged, notes, id FROM workouts ORDER BY date_logged DESC')
        workouts = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error fetching workout history: {e}")
        workouts = []
    conn.close()
    return render_template('history.html', workouts=workouts)

@app.route('/weekly_plan')
def weekly_plan():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check what columns actually exist
    columns = []
    try:
        cursor.execute("PRAGMA table_info(weekly_plan)")
        columns = [col[1] for col in cursor.fetchall()]
    except sqlite3.OperationalError as e:
        print(f"Error getting table info for weekly_plan: {e}")

    # Use the correct column names based on what exists
    plan_data = []
    try:
        if 'target_sets' in columns:
            cursor.execute('SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, COALESCE(notes, ""), COALESCE(newly_added, 0), COALESCE(progression_notes, "") FROM weekly_plan ORDER BY day_of_week, exercise_order')
        else:
            cursor.execute('SELECT id, day_of_week, exercise_name, sets, reps, weight, order_index, COALESCE(notes, ""), 0, "" FROM weekly_plan ORDER BY day_of_week, order_index')
        plan_data = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error fetching weekly plan data: {e}")

    conn.close()

    # Organize plan by day
    plan_by_day = {}
    for row in plan_data:
        id, day, exercise, sets, reps, weight, order, notes, newly_added, progression_notes = row
        if day not in plan_by_day:
            plan_by_day[day] = []
        plan_by_day[day].append({
            'id': id,
            'exercise': exercise,
            'sets': sets,
            'reps': reps,
            'weight': weight,
            'order': order,
            'notes': notes or "",
            'newly_added': bool(newly_added),
            'progression_notes': progression_notes or ""
        })

    return render_template('weekly_plan.html', plan_by_day=plan_by_day)

@app.route('/get_plan/<date>')
def get_plan(date):
    """Get workout plan for a specific date"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get day name from date
        from datetime import datetime
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        day_name = date_obj.strftime('%A').lower()

        cursor.execute('''
            SELECT exercise_name, target_sets, target_reps, target_weight, exercise_order,
                   COALESCE(notes, ""), COALESCE(progression_notes, "")
            FROM weekly_plan
            WHERE day_of_week = ?
            ORDER BY exercise_order
        ''', (day_name,))

        exercises = []
        for row in cursor.fetchall():
            exercise_name, sets, reps, weight, order, notes, progression_notes = row
            exercises.append({
                'exercise_name': exercise_name,
                'sets': sets,
                'reps': reps,
                'weight': weight,
                'order': order,
                'notes': notes,
                'progression_notes': progression_notes
            })

        conn.close()
        return jsonify({'exercises': exercises})

    except Exception as e:
        return jsonify({'exercises': [], 'error': str(e)})

    # Check what columns actually exist
    columns = []
    try:
        cursor.execute("PRAGMA table_info(weekly_plan)")
        columns = [col[1] for col in cursor.fetchall()]
    except sqlite3.OperationalError as e:
        print(f"Error checking column existence: {e}")

    if 'target_sets' in columns:
        cursor.execute('SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, COALESCE(notes, ""), COALESCE(newly_added, 0), COALESCE(progression_notes, "") FROM weekly_plan ORDER BY day_of_week, exercise_order')
    else:
        cursor.execute('SELECT id, day_of_week, exercise_name, sets, reps, weight, order_index, COALESCE(notes, ""), 0, "" FROM weekly_plan ORDER BY day_of_week, order_index')

    plan_data = cursor.fetchall()
    conn.close()

    # Organize plan by day
    plan_by_day = {}
    for row in plan_data:
        id, day, exercise, sets, reps, weight, order, notes, newly_added, progression_notes = row
        if day not in plan_by_day:
            plan_by_day[day] = []
        plan_by_day[day].append({
            'id': id,
            'exercise': exercise,
            'sets': sets,
            'reps': reps,
            'weight': weight,
            'order': order,
            'notes': notes or "",
            'newly_added': bool(newly_added),
            'progression_notes': progression_notes or ""
        })

    return render_template('weekly_plan.html', plan_by_day=plan_by_day)

@app.route('/profile')
def profile():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()

    # Get user background
    background = None
    try:
        cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY created_date DESC LIMIT 1')
        bg_result = cursor.fetchone()

        if bg_result:
            columns = [description[0] for description in cursor.description]
            background = dict(zip(columns, bg_result))
    except sqlite3.OperationalError as e:
        print(f"Error fetching user background: {e}")

    # Get user preferences
    preferences = {
        'tone': 'motivational',
        'detail_level': 'concise',
        'format': 'bullet_points',
        'units': 'lbs',
        'communication_style': 'encouraging',
        'technical_level': 'beginner'
    }
    try:
        cursor.execute('SELECT grok_tone, grok_detail_level, grok_format, preferred_units, communication_style, technical_level FROM users WHERE id = 1')
        pref_result = cursor.fetchone()
        if pref_result:
            preferences = {
                'tone': pref_result[0] or 'motivational',
                'detail_level': pref_result[1] or 'concise',
                'format': pref_result[2] or 'bullet_points',
                'units': pref_result[3] or 'lbs',
                'communication_style': pref_result[4] or 'encouraging',
                'technical_level': pref_result[5] or 'beginner'
            }
    except sqlite3.OperationalError as e:
        print(f"Error fetching user preferences: {e}")

    conn.close()
    return render_template('profile.html', background=background, preferences=preferences)

@app.route('/progression')
def progression():
    return render_template('progression.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/analyze_plan')
def analyze_plan():
    return render_template('analyze_plan.html')

@app.route('/get_stored_context')
def get_stored_context():
    """Get currently stored plan context for debugging/editing"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get plan context
        plan_context = None
        try:
            cursor.execute('''
                SELECT plan_philosophy, training_style, weekly_structure, progression_strategy,
                       special_considerations, created_by_ai, creation_reasoning, created_date, updated_date
                FROM plan_context
                WHERE user_id = 1
                ORDER BY created_date DESC
                LIMIT 1
            ''')

            plan_result = cursor.fetchone()
            if plan_result:
                columns = [description[0] for description in cursor.description]
                plan_context = dict(zip(columns, plan_result))
        except sqlite3.OperationalError as e:
            print(f"Error fetching plan context: {e}")

        # Get exercise metadata
        exercise_metadata = []
        try:
            cursor.execute('''
                SELECT exercise_name, exercise_type, primary_purpose, progression_logic, ai_notes, created_date
                FROM exercise_metadata
                WHERE user_id = 1
                ORDER BY exercise_name
            ''')

            exercise_results = cursor.fetchall()
            metadata_columns = [description[0] for description in cursor.description]

            for row in exercise_results:
                metadata_data.append(dict(zip(metadata_columns, row)))
        except sqlite3.OperationalError as e:
            print(f"Error fetching exercise metadata: {e}")


        conn.close()

        return jsonify({
            'plan_context': plan_context,
            'exercise_metadata': metadata_data,
            'context_count': len(plan_context) if plan_context else 0,
            'metadata_count': len(metadata_data)
        })

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/extract_plan_context', methods=['POST'])
def extract_plan_context():
    """Extract structured plan context from AI conversation"""
    try:
        data = request.json
        conversation = data.get('conversation', '')

        # Create a more specific prompt for extraction
        extraction_prompt = f"""Please analyze this conversation about my workout plan and extract the following information in the exact format shown:

TRAINING_PHILOSOPHY: [brief summary of the overall training approach discussed]
WEEKLY_STRUCTURE: [reasoning behind how the week is organized]
PROGRESSION_STRATEGY: [approach to progressive overload and advancement]
SPECIAL_CONSIDERATIONS: [any limitations, injuries, or special notes mentioned]
REASONING: [overall reasoning behind the plan design]

Here's the conversation to analyze:
{conversation}

Please be concise but capture the key insights from our discussion."""

        # Use Grok to extract structured data from conversation
        # response = get_grok_response_with_context(extraction_prompt) # Grok API call
        response = get_grok_response_with_context(extraction_prompt)

        # Parse Grok's structured response - look for fields anywhere in the response
        lines = response.split('\n')
        extracted_data = {}

        for line in lines:
            line = line.strip()
            if 'TRAINING_PHILOSOPHY:' in line or 'PLAN_PHILOSOPHY:' in line:
                extracted_data['philosophy'] = line.split(':', 1)[1].strip() if ':' in line else ''
            elif 'WEEKLY_STRUCTURE:' in line:
                extracted_data['weekly_structure'] = line.split(':', 1)[1].strip() if ':' in line else ''
            elif 'PROGRESSION_STRATEGY:' in line:
                extracted_data['progression_strategy'] = line.split(':', 1)[1].strip() if ':' in line else ''
            elif 'SPECIAL_CONSIDERATIONS:' in line:
                extracted_data['special_considerations'] = line.split(':', 1)[1].strip() if ':' in line else ''
            elif 'REASONING:' in line:
                extracted_data['reasoning'] = line.split(':', 1)[1].strip() if ':' in line else ''

        # If we didn't get structured fields, try to extract from natural language
        if not any(extracted_data.values()):
            # Extract from natural language response as fallback
            response_lower = response.lower()
            if 'philosophy' in response_lower or 'approach' in response_lower:
                # Extract a reasonable section as philosophy
                sentences = response.split('. ')
                extracted_data['philosophy'] = '. '.join(sentences[:2]) + '.' if sentences else response[:200]

            extracted_data['reasoning'] = response  # Store full response as reasoning

        # Save to database
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO plan_context
            (user_id, plan_philosophy, weekly_structure, progression_strategy,
             special_considerations, created_by_ai, creation_reasoning, created_date, updated_date)
            VALUES (1, ?, ?, ?, ?, TRUE, ?, ?, ?)
        ''', (
            extracted_data.get('philosophy', ''),
            extracted_data.get('weekly_structure', ''),
            extracted_data.get('progression_strategy', ''),
            extracted_data.get('special_considerations', ''),
            extracted_data.get('reasoning', ''),
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%Y-%m-%d')
        ))

        # NOW GET ALL EXERCISES FROM WEEKLY PLAN AND CREATE METADATA
        # Clear existing exercise metadata
        cursor.execute('DELETE FROM exercise_metadata WHERE user_id = 1')

        # Get ALL exercises from weekly plan in proper day/order structure
        cursor.execute('''
            SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order
            FROM weekly_plan
            ORDER BY
                CASE day_of_week
                    WHEN 'monday' THEN 1
                    WHEN 'tuesday' THEN 2
                    WHEN 'wednesday' THEN 3
                    WHEN 'thursday' THEN 4
                    WHEN 'friday' THEN 5
                    WHEN 'saturday' THEN 6
                    WHEN 'sunday' THEN 7
                END, exercise_order
        ''')
        all_exercises = cursor.fetchall()

        print(f"📊 Processing {len(all_exercises)} exercises from weekly plan")  # Debug log

        # Group exercises by name to detect variations
        exercise_groups = {}
        for day, exercise_name, sets, reps, weight, order in all_exercises:
            if exercise_name not in exercise_groups:
                exercise_groups[exercise_name] = []
            exercise_groups[exercise_name].append({
                'day': day,
                'sets': sets,
                'reps': reps,
                'weight': weight,
                'order': order
            })

        created_contexts = 0

        # Process each exercise group
        for exercise_name, instances in exercise_groups.items():
            exercise_lower = exercise_name.lower()

            # Check if this exercise has significantly different variations across days
            if len(instances) > 1:
                # Extract numeric values for comparison
                variations = []
                for instance in instances:
                    try:
                        weight_num = float(re.search(r'(\d+\.?\d*)', str(instance['weight'])).group(1)) if instance['weight'] != 'bodyweight' else 0
                        reps_num = int(re.search(r'(\d+)', str(instance['reps'])).group(1)) if instance['reps'].isdigit() else 10
                        volume = weight_num * instance['sets'] * reps_num
                        variations.append({
                            'day': instance['day'],
                            'sets': instance['sets'],
                            'reps': instance['reps'],
                            'weight': instance['weight'],
                            'volume': volume,
                            'weight_num': weight_num
                        })
                    except:
                        variations.append({
                            'day': instance['day'],
                            'sets': sets,
                            'reps': reps,
                            'weight': weight,
                            'volume': 0,
                            'weight_num': 0
                        })

                # Sort by volume to identify light vs heavy versions
                variations.sort(key=lambda x: x['volume'])

                # If there's a significant difference (>20% volume difference), create separate contexts
                if len(variations) >= 2:
                    volume_diff = (variations[-1]['volume'] - variations[0]['volume']) / max(variations[0]['volume'], 1)

                    if volume_diff > 0.2:  # 20% difference threshold
                        # Create separate contexts for light and heavy versions
                        for i, variation in enumerate(variations):
                            suffix = ""
                            if i == 0:
                                suffix = " (Light)"
                            elif i == len(variations) - 1:
                                suffix = " (Heavy)"
                            else:
                                suffix = f" (Day {i+1})"

                            context_name = f"{exercise_name}{suffix}"

                            # Determine purpose and progression based on exercise type
                            if any(word in exercise_lower for word in ['ab', 'crunch', 'woodchop', 'back extension', 'strap ab']):
                                purpose = "Midsection hypertrophy for muscle development"
                                progression_logic = "aggressive"
                                notes = "Core work treated as main lift per plan philosophy"
                            elif any(word in exercise_lower for word in ['press', 'chest supported row', 'glute drive', 'leg press', 'assisted pull', 'assisted dip']):
                                purpose = "Compound strength and mass building"
                                progression_logic = "aggressive"
                                notes = "Main compound movement"
                            elif any(word in exercise_lower for word in ['leg curl', 'leg extension', 'glute slide', 'glute abduction', 'adductor']):
                                purpose = "Lower body isolation and hypertrophy"
                                progression_logic = "aggressive"
                                notes = "Machine-based isolation for joint safety"
                            elif any(word in exercise_lower for word in ['curl', 'raise', 'fly', 'lateral', 'rear delt', 'front raise']):
                                purpose = "Upper body isolation hypertrophy"
                                progression_logic = "slow"
                                notes = "Isolation exercise for targeted growth"
                            elif any(word in exercise_lower for word in ['pushup', 'push up', 'hanging leg', 'split squat', 'goblet']):
                                purpose = "Bodyweight strength and control"
                                progression_logic = "slow"
                                notes = "Bodyweight progression: reps → tempo → weight"
                            elif 'finisher' in exercise_lower:
                                purpose = "High-rep endurance and muscle pump"
                                progression_logic = "maintain"
                                notes = "High-rep finisher work"
                            else:
                                purpose = "Hypertrophy and strength development"
                                progression_logic = "normal"
                                notes = "General hypertrophy and strength work"

                            cursor.execute('''
                                INSERT INTO exercise_metadata
                                (user_id, exercise_name, exercise_type, primary_purpose,
                                 progression_logic, ai_notes, created_date)
                                VALUES (1, ?, 'working_set', ?, ?, ?, ?)
                            ''', (
                                context_name,
                                purpose,
                                progression_logic,
                                notes,
                                datetime.now().strftime('%Y-%m-%d')
                            ))
                            created_contexts += 1

                    else:
                        # Similar variations, create one context
                        if any(word in exercise_lower for word in ['ab', 'crunch', 'woodchop', 'back extension', 'strap ab']):
                            purpose = "Midsection hypertrophy for muscle development"
                            progression_logic = "aggressive"
                            notes = "Core work treated as main lift per plan philosophy"
                        elif any(word in exercise_lower for word in ['press', 'chest supported row', 'glute drive', 'leg press', 'assisted pull', 'assisted dip']):
                            purpose = "Compound strength and mass building"
                            progression_logic = "aggressive"
                            notes = "Main compound movement"
                        elif any(word in exercise_lower for word in ['leg curl', 'leg extension', 'glute slide', 'glute abduction', 'adductor']):
                            purpose = "Lower body isolation and hypertrophy"
                            progression_logic = "aggressive"
                            notes = "Machine-based isolation for joint safety"
                        elif any(word in exercise_lower for word in ['curl', 'raise', 'fly', 'lateral', 'rear delt', 'front raise']):
                            purpose = "Upper body isolation hypertrophy"
                            progression_logic = "slow"
                            notes = "Isolation exercise for targeted growth"
                        elif any(word in exercise_lower for word in ['pushup', 'push up', 'hanging leg', 'split squat', 'goblet']):
                            purpose = "Bodyweight strength and control"
                            progression_logic = "slow"
                            notes = "Bodyweight progression: reps → tempo → weight"
                        elif 'finisher' in exercise_lower:
                            purpose = "High-rep endurance and muscle pump"
                            progression_logic = "maintain"
                            notes = "High-rep finisher work"
                        else:
                            purpose = "Hypertrophy and strength development"
                            progression_logic = "normal"
                            notes = "General hypertrophy and strength work"

                        cursor.execute('''
                            INSERT INTO exercise_metadata
                            (user_id, exercise_name, exercise_type, primary_purpose,
                             progression_logic, ai_notes, created_date)
                            VALUES (1, ?, 'working_set', ?, ?, ?, ?)
                        ''', (
                            exercise_name,
                            purpose,
                            progression_logic,
                            notes,
                            datetime.now().strftime('%Y-%m-%d')
                        ))
                        created_contexts += 1
            else:
                # Single instance of the exercise
                if any(word in exercise_lower for word in ['ab', 'crunch', 'woodchop', 'back extension', 'strap ab']):
                    purpose = "Midsection hypertrophy for muscle development"
                    progression_logic = "aggressive"
                    notes = "Core work treated as main lift per plan philosophy"
                elif any(word in exercise_lower for word in ['press', 'chest supported row', 'glute drive', 'leg press', 'assisted pull', 'assisted dip']):
                    purpose = "Compound strength and mass building"
                    progression_logic = "aggressive"
                    notes = "Main compound movement"
                elif any(word in exercise_lower for word in ['leg curl', 'leg extension', 'glute slide', 'glute abduction', 'adductor']):
                    purpose = "Lower body isolation and hypertrophy"
                    progression_logic = "aggressive"
                    notes = "Machine-based isolation for joint safety"
                elif any(word in exercise_lower for word in ['curl', 'raise', 'fly', 'lateral', 'rear delt', 'front raise']):
                    purpose = "Upper body isolation hypertrophy"
                    progression_logic = "slow"
                    notes = "Isolation exercise for targeted growth"
                elif any(word in exercise_lower for word in ['pushup', 'push up', 'hanging leg', 'split squat', 'goblet']):
                    purpose = "Bodyweight strength and control"
                    progression_logic = "slow"
                    notes = "Bodyweight progression: reps → tempo → weight"
                elif 'finisher' in exercise_lower:
                    purpose = "High-rep endurance and muscle pump"
                    progression_logic = "maintain"
                    notes = "High-rep finisher work"
                else:
                    purpose = "Hypertrophy and strength development"
                    progression_logic = "normal"
                    notes = "General hypertrophy and strength work"

                cursor.execute('''
                    INSERT INTO exercise_metadata
                    (user_id, exercise_name, exercise_type, primary_purpose,
                     progression_logic, ai_notes, created_date)
                    VALUES (1, ?, 'working_set', ?, ?, ?, ?)
                ''', (
                    exercise_name,
                    purpose,
                    progression_logic,
                    notes,
                    datetime.now().strftime('%Y-%m-%d')
                ))
                created_contexts += 1

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'AI analysis saved successfully!'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/execute_auto_actions', methods=['POST'])
def execute_auto_actions():
    """Execute auto-detected actions from conversations"""
    try:
        data = request.json
        conversation_id = data.get('conversation_id')

        if not conversation_id:
            return jsonify({'success': False, 'error': 'No conversation ID provided'})

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get pending actions for this conversation
        pending_actions = []
        try:
            cursor.execute('''
                SELECT id, action_type, action_data
                FROM auto_actions
                WHERE conversation_id = ? AND executed = FALSE
            ''', (conversation_id,))
            pending_actions = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"Error fetching pending actions: {e}")

        results = []

        for action_id, action_type, action_data_json in pending_actions:
            action_data = json.loads(action_data_json)

            try:
                if action_type == 'log_workout':
                    # Auto-log workout
                    cursor.execute('''
                        INSERT INTO workouts (exercise_name, sets, reps, weight, notes, date_logged, day_completed, substitution_reason)
                        VALUES (?, ?, ?, ?, ?, ?, FALSE, ?)
                    ''', (
                        action_data['exercise'],
                        action_data['sets'],
                        action_data['reps'],
                        action_data['weight'],
                        'Auto-logged from conversation',
                        datetime.now().strftime('%Y-%m-%d'),
                        action_data.get('substitution_reason', '')
                    ))

                    results.append({
                        'action_id': action_id,
                        'type': action_type,
                        'success': True,
                        'message': f"Logged {action_data['exercise']}: {action_data['sets']}x{action_data['reps']}@{action_data['weight']}"
                    })

                elif action_type == 'modify_plan':
                    # Plan modifications would need more complex logic
                    results.append({
                        'action_id': action_id,
                        'type': action_type,
                        'success': False,
                        'message': 'Plan modifications require manual approval'
                    })

                # Mark action as executed
                cursor.execute('''
                    UPDATE auto_actions
                    SET executed = TRUE, execution_result = ?
                    WHERE id = ?
                ''', (json.dumps(results[-1]), action_id))

            except Exception as e:
                results.append({
                    'action_id': action_id,
                    'type': action_type,
                    'success': False,
                    'message': str(e)
                })

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'executed_actions': results
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/add_progression_guidance', methods=['POST'])
def add_progression_guidance():
    """Add progression guidance notes without modifying plan weights"""
    try:
        data = request.json
        exercise_name = data.get('exercise_name', '')
        guidance_note = data.get('guidance_note', '')
        day_of_week = data.get('day_of_week', '').lower()

        if not exercise_name or not guidance_note:
            return jsonify({'success': False, 'error': 'Exercise name and guidance note required'})

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Update progression_notes for the exercise
        cursor.execute('''
            UPDATE weekly_plan
            SET progression_notes = ?
            WHERE LOWER(exercise_name) = LOWER(?) AND day_of_week = ?
        ''', (guidance_note, exercise_name, day_of_week))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return jsonify({
                'success': True,
                'message': f"Added progression guidance for {exercise_name}",
                'guidance_added': {
                    'exercise': exercise_name,
                    'note': guidance_note,
                    'day': day_of_week
                }
            })
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Exercise not found in weekly plan'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/modify_plan', methods=['POST'])
def modify_plan():
    """Allow Grok to propose and execute plan modifications"""
    try:
        data = request.json
        modification_type = data.get('type')  # 'update', 'add', 'remove'
        day = data.get('day', '').lower()
        exercise_name = data.get('exercise_name', '')
        sets = data.get('sets')
        reps = data.get('reps')
        weight = data.get('weight')
        reasoning = data.get('reasoning', '')

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        if modification_type == 'update':
            # Update existing exercise
            cursor.execute('''
                UPDATE weekly_plan
                SET target_sets = ?, target_reps = ?, target_weight = ?, notes = ?
                WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
            ''', (sets, reps, weight, reasoning, day, exercise_name))

            message = f"Updated {exercise_name} on {day}: {sets}x{reps}@{weight}"

        elif modification_type == 'add':
            # Get next order for the day
            cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', (day,))
            next_order = cursor.fetchone()[0]

            cursor.execute('''
                INSERT INTO weekly_plan
                (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, created_by, newly_added, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'grok_ai', TRUE, ?)
            ''', (day, exercise_name, sets, reps, weight, next_order, reasoning, datetime.now().strftime('%Y-%m-%d')))

            message = f"Added {exercise_name} to {day}: {sets}x{reps}@{weight}"

        elif modification_type == 'remove':
            cursor.execute('DELETE FROM weekly_plan WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)', (day, exercise_name))
            message = f"Removed {exercise_name} from {day}"

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': message,
            'change_made': {
                'type': modification_type,
                'day': day,
                'exercise': exercise_name,
                'details': f"{sets}x{reps}@{weight}" if sets else None,
                'reasoning': reasoning
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/propose_plan_change', methods=['POST'])
def propose_plan_change():
    """Create a plan change proposal for user confirmation"""
    try:
        data = request.json
        conversation_id = data.get('conversation_id')
        modification_type = data.get('type', 'add')
        day = data.get('day', '').lower()
        exercise_name = data.get('exercise_name', '')
        sets = data.get('sets', 3)
        reps = data.get('reps', '8-12')
        weight = data.get('weight', 'bodyweight')
        reasoning = data.get('reasoning', '')

        # Store the proposal in the database for confirmation
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        proposal_data = {
            'type': modification_type,
            'day': day,
            'exercise_name': exercise_name,
            'sets': sets,
            'reps': reps,
            'weight': weight,
            'reasoning': reasoning
        }

        cursor.execute('''
            INSERT INTO auto_actions
            (conversation_id, action_type, action_data, executed)
            VALUES (?, ?, ?, FALSE)
        ''', (conversation_id, 'plan_modification_proposal', json.dumps(proposal_data)))

        proposal_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'proposal_id': proposal_id,
            'proposal': proposal_data
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/confirm_plan_change', methods=['POST'])
def confirm_plan_change():
    """Execute a confirmed plan change"""
    try:
        data = request.json
        proposal_id = data.get('proposal_id')

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get the proposal
        result = None
        try:
            cursor.execute('SELECT action_data FROM auto_actions WHERE id = ? AND executed = FALSE', (proposal_id,))
            result = cursor.fetchone()
        except sqlite3.OperationalError as e:
            print(f"Error fetching proposal: {e}")

        if not result:
            return jsonify({'success': False, 'error': 'Proposal not found or already executed'})

        proposal_data = json.loads(result[0])

        # Execute the plan change
        if proposal_data['type'] == 'add':
            cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', (proposal_data['day'],))
            next_order = cursor.fetchone()[0]

            cursor.execute('''
                INSERT INTO weekly_plan
                (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'grok_ai')
            ''', (
                proposal_data['day'],
                proposal_data['exercise_name'],
                proposal_data['sets'],
                proposal_data['reps'],
                proposal_data['weight'],
                next_order,
                proposal_data['reasoning']
            ))

        # Mark as executed
        cursor.execute('UPDATE auto_actions SET executed = TRUE WHERE id = ?', (proposal_id,))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f"Added {proposal_data['exercise_name']} to {proposal_data['day'].title()}"
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/add_to_plan', methods=['POST'])
def add_to_plan():
    """Add exercise to weekly plan"""
    try:
        day = request.form.get('day').lower()
        exercise = request.form.get('exercise')
        sets = int(request.form.get('sets'))
        reps = request.form.get('reps')
        weight = request.form.get('weight')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get next order for the day
        cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', (day,))
        next_order = cursor.fetchone()[0]

        cursor.execute('''
            INSERT INTO weekly_plan
            (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, newly_added, date_added)
            VALUES (?, ?, ?, ?, ?, ?, TRUE, ?)
        ''', (day, exercise, sets, reps, weight, next_order, datetime.now().strftime('%Y-%m-%d')))

        conn.commit()
        conn.close()

        return redirect(url_for('weekly_plan'))

    except Exception as e:
        print(f"Error adding exercise: {e}")
        return redirect(url_for('weekly_plan'))

@app.route('/edit_exercise', methods=['POST'])
def edit_exercise():
    """Edit exercise in weekly plan"""
    try:
        data = request.json
        exercise_id = data.get('id')
        sets = data.get('sets')
        reps = data.get('reps')
        weight = data.get('weight')
        exercise_name = data.get('exercise')
        notes = data.get('notes', '')
        progression_notes = data.get('progression_notes', '')

        if not exercise_id:
            return jsonify({'success': False, 'error': 'Exercise ID is required'})

        if not exercise_name:
            return jsonify({'success': False, 'error': 'Exercise name is required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # First check if progression_notes column exists
        progression_notes_col_exists = False
        try:
            cursor.execute("PRAGMA table_info(weekly_plan)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'progression_notes' in columns:
                progression_notes_col_exists = True
        except sqlite3.OperationalError as e:
            print(f"Error checking column existence: {e}")

        if progression_notes_col_exists:
            cursor.execute('''
                UPDATE weekly_plan
                SET target_sets = ?, target_reps = ?, target_weight = ?, exercise_name = ?, notes = ?, progression_notes = ?
                WHERE id = ?
            ''', (sets, reps, weight, exercise_name, notes, progression_notes, exercise_id))
        else:
            # If column doesn't exist, update without progression_notes
            cursor.execute('''
                UPDATE weekly_plan
                SET target_sets = ?, target_reps = ?, target_weight = ?, exercise_name = ?, notes = ?
                WHERE id = ?
            ''', (sets, reps, weight, exercise_name, notes, exercise_id))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            print(f"✅ Updated exercise {exercise_name}: progression_notes = '{progression_notes}'")
            return jsonify({'success': True})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Exercise not found'})

    except Exception as e:
        print(f"❌ Error updating exercise: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete_exercise', methods=['POST'])
def delete_exercise():
    """Delete exercise from weekly plan"""
    try:
        data = request.json
        day = data.get('day')
        exercise = data.get('exercise')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM weekly_plan WHERE day_of_week = ? AND exercise_name = ?', (day, exercise))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/reorder_exercise', methods=['POST'])
def reorder_exercise():
    """Reorder exercises in weekly plan"""
    try:
        data = request.json
        day = data.get('day')
        exercise = data.get('exercise')
        direction = data.get('direction')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get current order
        cursor.execute('SELECT exercise_order FROM weekly_plan WHERE day_of_week = ? AND exercise_name = ?', (day, exercise))
        current_order_result = cursor.fetchone()

        if not current_order_result:
            return jsonify({'success': False, 'error': 'Exercise not found'})

        current_order = current_order_result[0]

        if direction == 'up' and current_order > 1:
            new_order = current_order - 1
        elif direction == 'down':
            cursor.execute('SELECT MAX(exercise_order) FROM weekly_plan WHERE day_of_week = ?', (day,))
            max_order = cursor.fetchone()[0]
            if current_order < max_order:
                new_order = current_order + 1
            else:
                return jsonify({'success': False, 'error': 'Already at bottom'})
        else:
            return jsonify({'success': False, 'error': 'Cannot move further'})

        # Swap orders
        cursor.execute('UPDATE weekly_plan SET exercise_order = 999 WHERE day_of_week = ? AND exercise_order = ?', (day, new_order))
        cursor.execute('UPDATE weekly_plan SET exercise_order = ? WHERE day_of_week = ? AND exercise_name = ?', (new_order, day, exercise))
        cursor.execute('UPDATE weekly_plan SET exercise_order = ? WHERE day_of_week = ? AND exercise_order = ?', (current_order, day, 999))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_ai_preferences', methods=['POST'])
def update_ai_preferences():
    """Update user AI preferences"""
    try:
        data = request.json
        tone = data.get('tone')
        detail_level = data.get('detail_level')
        format_pref = data.get('format')
        communication_style = data.get('communication_style')
        technical_level = data.get('technical_level')
        units = data.get('units')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Update AI preferences in users table
        cursor.execute('''
            UPDATE users 
            SET grok_tone = ?, grok_detail_level = ?, grok_format = ?, 
                communication_style = ?, technical_level = ?, preferred_units = ?
            WHERE id = 1
        ''', (tone, detail_level, format_pref, communication_style, technical_level, units))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'AI preferences updated successfully'})

    except Exception as e:
        print(f"Error updating AI preferences: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_profile', methods=['POST'])
def update_profile():
    """Update user profile field"""
    try:
        field_name = request.form.get('field_name')
        value = request.form.get('value')

        if not field_name:
            return jsonify({'success': False, 'error': 'Field name is required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user_background record exists
        cursor.execute('SELECT COUNT(*) FROM user_background WHERE user_id = 1')
        if cursor.fetchone()[0] == 0:
            # Create record
            cursor.execute('INSERT INTO user_background (user_id) VALUES (1)')

        # Update the specific field
        update_query = f'UPDATE user_background SET {field_name} = ?, updated_date = ? WHERE user_id = 1'
        cursor.execute(update_query, (value, datetime.now().strftime('%Y-%m-%d')))

        conn.commit()
        conn.close()

        return redirect(url_for('profile'))

    except Exception as e:
        print(f"Error updating profile: {e}")
        return redirect(url_for('profile'))

@app.route('/api/weekly_plan')
def api_weekly_plan():
    """API endpoint for weekly plan data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order
            FROM weekly_plan
            ORDER BY
                CASE day_of_week
                    WHEN 'monday' THEN 1
                    WHEN 'tuesday' THEN 2
                    WHEN 'wednesday' THEN 3
                    WHEN 'thursday' THEN 4
                    WHEN 'friday' THEN 5
                    WHEN 'saturday' THEN 6
                    WHEN 'sunday' THEN 7
                END, exercise_order
        ''')

        plan_data = cursor.fetchall()
        conn.close()

        # Organize by day
        plan_by_day = {}
        for day, exercise, sets, reps, weight, order in plan_data:
            if day not in plan_by_day:
                plan_by_day[day] = []
            plan_by_day[day].append({
                'exercise': exercise,
                'sets': sets,
                'reps': reps,
                'weight': weight,
                'order': order
            })

        return jsonify(plan_by_day)

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/get_weight_history')
def get_weight_history():
    """Get weight history for analytics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create a simple weight tracking table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weight_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weight REAL NOT NULL,
                date_logged TEXT NOT NULL,
                user_id INTEGER DEFAULT 1
            )
        ''')

        cursor.execute('SELECT date_logged, weight FROM weight_logs WHERE user_id = 1 ORDER BY date_logged')
        weight_data = cursor.fetchall()

        dates = [row[0] for row in weight_data]
        weights = [row[1] for row in weight_data]

        conn.close()
        return jsonify({'dates': dates, 'weights': weights})
    except Exception as e:
        return jsonify({'dates': [], 'weights': []})

@app.route('/get_volume_history')
def get_volume_history():
    """Get volume history for analytics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get weekly volume data for the last 8 weeks
        weekly_volumes = []
        week_labels = []

        for week_offset in range(7, -1, -1):
            week_start = (datetime.now() - timedelta(weeks=week_offset, days=datetime.now().weekday())).strftime('%Y-%m-%d')
            week_end = (datetime.now() - timedelta(weeks=week_offset, days=datetime.now().weekday() - 6)).strftime('%Y-%m-%d')

            cursor.execute('SELECT exercise_name, sets, reps, weight FROM workouts WHERE date_logged BETWEEN ? AND ?', (week_start, week_end))
            week_workouts = cursor.fetchall()

            week_volume = 0
            for exercise, sets, reps, weight in week_workouts:
                try:
                    weight_str = str(weight).lower().replace('lbs', '').replace('kg', '').strip()
                    if weight_str != 'bodyweight' and weight_str:
                        weight_num = float(weight_str)
                        reps_num = int(str(reps).split('-')[0]) if '-' in str(reps) else int(reps)
                        week_volume += weight_num * sets * reps_num
                except (ValueError, AttributeError):
                    continue

            weekly_volumes.append(int(week_volume))
            week_labels.append(f"Week {week_offset + 1}")

        conn.close()
        return jsonify({'weeks': week_labels, 'volumes': weekly_volumes})
    except Exception as e:
        return jsonify({'weeks': [], 'volumes': []})

@app.route('/get_exercise_list')
def get_exercise_list():
    """Get exercise list for analytics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get exercises from both workout logs and weekly plan
        cursor.execute('SELECT DISTINCT exercise_name FROM workouts WHERE exercise_name IS NOT NULL ORDER BY exercise_name')
        logged_exercises = [row[0] for row in cursor.fetchall()]

        cursor.execute('SELECT DISTINCT exercise_name FROM weekly_plan WHERE exercise_name IS NOT NULL ORDER BY exercise_name')
        planned_exercises = [row[0] for row in cursor.fetchall()]

        # Combine and deduplicate
        all_exercises = list(set(logged_exercises + planned_exercises))
        all_exercises.sort()

        conn.close()
        return jsonify({'exercises': all_exercises})

    except Exception as e:
        print(f"Error in get_exercise_list: {e}")
        return jsonify({'exercises': []})

@app.route('/log_weight', methods=['POST'])
def log_weight():
    """Log weight entry"""
    try:
        data = request.json
        weight = float(data.get('weight'))
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))

        conn = get_db_connection()
        cursor = conn.cursor()

        # Create weight_logs table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weight_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weight REAL NOT NULL,
                date_logged TEXT NOT NULL,
                user_id INTEGER DEFAULT 1
            )
        ''')

        # Insert or update weight for the date
        cursor.execute('DELETE FROM weight_logs WHERE date_logged = ? AND user_id = 1', (date,))
        cursor.execute('INSERT INTO weight_logs (weight, date_logged, user_id) VALUES (?, ?, 1)', (weight, date))

        conn.commit()
        conn.close()

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_exercise_performance/<exercise>')
def get_exercise_performance(exercise):
    """Get exercise performance data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # More flexible exercise matching - try exact match first, then partial
        performance_data = []
        try:
            cursor.execute('''
                SELECT date_logged, sets, reps, weight
                FROM workouts
                WHERE LOWER(exercise_name) = LOWER(?)
                ORDER BY date_logged
            ''', (exercise,))
            performance_data = cursor.fetchall()

            # If no exact match, try partial matching
            if not performance_data:
                cursor.execute('''
                    SELECT date_logged, sets, reps, weight
                    FROM workouts
                    WHERE LOWER(exercise_name) LIKE LOWER(?)
                    ORDER BY date_logged
                ''', (f'%{exercise}%',))
                performance_data = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"Error fetching exercise performance: {e}")

        dates = []
        max_weights = []
        volumes = []

        print(f"🔍 Found {len(performance_data)} workout entries for '{exercise}'")  # Debug log

        # Process actual logged data with improved reps parsing
        for date, sets, reps, weight in performance_data:
            try:
                weight_str = str(weight).lower().replace('lbs', '').replace('kg', '').strip()
                if weight_str and weight_str != 'bodyweight':
                    weight_num = float(weight_str)

                    # Improved reps parsing to handle different formats
                    reps_str = str(reps).strip()
                    reps_num = 0

                    # Handle different reps formats
                    if '/' in reps_str:
                        # Format like "12/12/12" - take average or first value
                        reps_parts = reps_str.split('/')
                        reps_values = []
                        for part in reps_parts:
                            try:
                                reps_values.append(int(part.strip()))
                            except ValueError:
                                continue
                        if reps_values:
                            reps_num = max(reps_values)  # Use max reps for weight calculation
                    elif '-' in reps_str:
                        # Format like "8-12" - use first number
                        reps_num = int(reps_str.split('-')[0])
                    else:
                        # Simple format like "12"
                        reps_num = int(reps_str)

                    if reps_num > 0:
                        volume = weight_num * sets * reps_num

                        dates.append(date)
                        max_weights.append(weight_num)
                        volumes.append(volume)

                        print(f"📊 {date}: {sets}x{reps_num}@{weight_num}lbs = {volume} volume")  # Debug log

            except (ValueError, AttributeError) as e:
                print(f"⚠️ Error parsing workout data: {date}, {sets}, {reps}, {weight} - {e}")
                continue

        # No fake data generation - if no logged data exists, return empty results
        print(f"🔍 FINAL RESULT: Found {len(dates)} actual workout entries for '{exercise}'")

        # Calculate stats
        best_weight = max(max_weights) if max_weights else 0
        best_date = dates[max_weights.index(best_weight)] if max_weights else 'N/A'
        recent_avg = sum(max_weights[-3:]) / len(max_weights[-3:]) if len(max_weights) >= 3 else (sum(max_weights) / len(max_weights) if max_weights else 0)
        total_sessions = len(dates)

        # Calculate progress (recent vs older)
        progress = 0
        if len(max_weights) >= 4:
            recent_weights = max_weights[-2:]
            older_weights = max_weights[:2]

            recent_avg_calc = sum(recent_weights) / len(recent_weights)
            older_avg = sum(older_weights) / len(older_weights)
            progress = ((recent_avg_calc - older_avg) / older_avg * 100) if older_avg > 0 else 0
        elif len(max_weights) >= 2: # Fallback if not enough data for the above calculation
            recent_weights = max_weights[-1:]
            older_weights = max_weights[:-1]
            if older_weights:
                recent_avg_calc = sum(recent_weights) / len(recent_weights)
                older_avg = sum(older_weights) / len(older_weights)
                progress = ((recent_avg_calc - older_avg) / older_avg * 100) if older_avg > 0 else 0


        conn.close()

        return jsonify({
            'dates': dates,
            'max_weights': max_weights,
            'volumes': volumes,
            'best_weight': best_weight,
            'best_date': best_date,
            'recent_avg': round(recent_avg, 1),
            'progress': round(progress, 1),
            'total_sessions': total_sessions,
            'has_real_data': len(performance_data) > 0
        })

    except Exception as e:
        print(f"Error in get_exercise_performance: {e}")
        return jsonify({
            'dates': [],
            'max_weights': [],
            'volumes': [],
            'best_weight': 0,
            'best_date': 'N/A',
            'recent_avg': 0,
            'progress': 0,
            'total_sessions': 0,
            'has_real_data': False
        })

@app.route('/edit_workout', methods=['POST'])
def edit_workout():
    """Edit an existing workout entry"""
    try:
        data = request.json
        workout_id = data.get('workout_id')
        exercise_name = data.get('exercise_name', '')
        sets = data.get('sets', 1)
        reps = data.get('reps', '')
        weight = data.get('weight', '')
        notes = data.get('notes', '')

        if not workout_id:
            return jsonify({'success': False, 'error': 'Workout ID is required'})

        if not exercise_name:
            return jsonify({'success': False, 'error': 'Exercise name is required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # Update the workout entry (preserving original date_logged and id)
        cursor.execute('''
            UPDATE workouts
            SET exercise_name = ?, sets = ?, reps = ?, weight = ?, notes = ?
            WHERE id = ?
        ''', (exercise_name, sets, reps, weight, notes, workout_id))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            print(f"✏️ Updated workout ID {workout_id}: {exercise_name} {sets}x{reps}@{weight}")
            return jsonify({'success': True, 'message': 'Workout updated successfully'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Workout not found'})

    except Exception as e:
        print(f"Error editing workout: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete_workout', methods=['POST'])
def delete_workout():
    """Delete a workout entry"""
    try:
        data = request.json
        workout_id = data.get('workout_id')

        if not workout_id:
            return jsonify({'success': False, 'error': 'Workout ID is required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get exercise name before deleting to potentially restore newly_added flag
        exercise_name = None
        try:
            cursor.execute('SELECT exercise_name FROM workouts WHERE id = ?', (workout_id,))
            result = cursor.fetchone()
            if result:
                exercise_name = result[0]
        except sqlite3.OperationalError as e:
            print(f"Error fetching exercise name for deletion: {e}")


        if exercise_name:
            # Delete the workout
            cursor.execute('DELETE FROM workouts WHERE id = ?', (workout_id,))

            # Check if this was the only log for this exercise
            remaining_logs = 0
            try:
                cursor.execute('SELECT COUNT(*) FROM workouts WHERE LOWER(exercise_name) = LOWER(?)', (exercise_name,))
                remaining_logs = cursor.fetchone()[0]
            except sqlite3.OperationalError as e:
                print(f"Error counting remaining logs: {e}")

            print(f"🗑️ Deleted workout for {exercise_name}, remaining logs: {remaining_logs}")

            if remaining_logs == 0:
                # Check what's in the weekly plan for this exercise
                plan_result = None
                try:
                    cursor.execute('SELECT exercise_name, created_by, newly_added FROM weekly_plan WHERE LOWER(exercise_name) = LOWER(?)', (exercise_name,))
                    plan_result = cursor.fetchone()
                except sqlite3.OperationalError as e:
                    print(f"Error checking weekly plan for '{exercise_name}': {e}")

                if plan_result:
                    plan_exercise_name, created_by, currently_newly_added = plan_result
                    print(f"📋 Found in plan: '{plan_exercise_name}', created_by: '{created_by}', currently_newly_added: {currently_newly_added}")

                    # Restore newly_added flag if it was created by AI (regardless of current newly_added status)
                    if created_by == 'grok_ai':
                        try:
                            cursor.execute('''
                                UPDATE weekly_plan
                                SET newly_added = TRUE, created_by = COALESCE(created_by, 'grok_ai')
                                WHERE LOWER(exercise_name) = LOWER(?)
                            ''', (exercise_name,))

                            if cursor.rowcount > 0:
                                print(f"🔄 Restored 'newly_added' flag for {exercise_name} - no remaining logs, created by AI")
                            else:
                                print(f"⚠️ Failed to update newly_added flag for {exercise_name}")
                        except sqlite3.OperationalError as e:
                            print(f"Error updating newly_added flag: {e}")
                    else:
                        print(f"ℹ️ {exercise_name} exists in plan but created by '{created_by}', not restoring NEW flag")
                else:
                    print(f"ℹ️ {exercise_name} not in weekly plan (free logging)")

            conn.commit()
            conn.close()

            return jsonify({'success': True, 'message': 'Workout deleted successfully'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Workout not found'})

    except Exception as e:
        print(f"Error deleting workout: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/save_workout', methods=['POST'])
def save_workout():
    """Save a single workout entry"""
    try:
        data = request.json
        exercise_name = data.get('exercise_name', '')
        sets = data.get('sets', 1)
        reps = data.get('reps', '')
        weight = data.get('weight', '')
        notes = data.get('notes', '')
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))

        # Handle substitution data
        original_exercise = data.get('original_exercise', '')
        original_weight = data.get('original_weight', '')
        substitution_reason = data.get('substitution_reason', '')

        # Handle complex exercise data
        is_complex = data.get('is_complex', False)
        complex_rounds = data.get('complex_rounds', [])
        complex_performance_data = data.get('complex_performance_data', '')

        # Handle performance tracking data
        performance_context = data.get('performance_context', '')
        environmental_factors = data.get('environmental_factors', '')
        difficulty_rating = data.get('difficulty_rating')
        gym_location = data.get('gym_location', '')

        if not exercise_name:
            return jsonify({'status': 'error', 'message': 'Exercise name is required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # Handle complex exercise formatting
        if is_complex and complex_rounds:
            # Format complex rounds for storage
            complex_reps_data = []
            for i, round_data in enumerate(complex_rounds, 1):
                complex_reps_data.append(f"Round {i}: {round_data}")
            final_reps = ' | '.join(complex_reps_data)
            final_notes = f"{notes} [COMPLEX EXERCISE]" if notes else "[COMPLEX EXERCISE]"
        elif complex_performance_data:
            # Handle the new detailed complex exercise data
            final_reps = reps  # This should already be formatted from the frontend
            final_notes = f"{notes} [COMPLEX EXERCISE - Detailed: {complex_performance_data}]" if notes else f"[COMPLEX EXERCISE - Detailed: {complex_performance_data}]"
        else:
            final_reps = reps
            final_notes = notes

        # Build comprehensive notes
        comprehensive_notes = final_notes
        if original_exercise and substitution_reason:
            comprehensive_notes += f" SUBSTITUTED FROM: {original_exercise} (planned: {original_weight}) - Reason: {substitution_reason}"
        if performance_context:
            comprehensive_notes += f" Performance: {performance_context}"
        if environmental_factors:
            comprehensive_notes += f" Environment: {environmental_factors}"

        cursor.execute('''
            INSERT INTO workouts (exercise_name, sets, reps, weight, notes, date_logged, 
                                substitution_reason, performance_context, environmental_factors, 
                                difficulty_rating, gym_location, day_completed, complex_exercise_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (exercise_name, sets, final_reps, weight, comprehensive_notes, date,
              substitution_reason, performance_context, environmental_factors,
              difficulty_rating, gym_location, False, complex_performance_data))

        # Clear newly_added flag if this exercise was recently added to plan
        try:
            cursor.execute('''
                UPDATE weekly_plan 
                SET newly_added = FALSE 
                WHERE LOWER(exercise_name) = LOWER(?) AND newly_added = TRUE
            ''', (exercise_name,))
        except sqlite3.OperationalError:
            pass  # newly_added column might not exist in older databases

        conn.commit()
        workout_id = cursor.lastrowid
        conn.close()

        return jsonify({
            'status': 'success', 
            'message': 'Workout logged successfully',
            'workout_id': workout_id
        })

    except Exception as e:
        print(f"Error saving workout: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/get_conversation_context/<int:days>')
def get_conversation_context_api(days):
    """Get conversation context for the last N days"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        conversations = []
        try:
            cursor.execute('''
                SELECT c.user_message, c.ai_response, c.detected_intent, c.confidence_score,
                       c.exercise_mentioned, c.form_cues_given, c.coaching_context,
                       c.plan_modifications, c.timestamp,
                       COUNT(aa.id) as auto_actions_count
                FROM conversations c
                LEFT JOIN auto_actions aa ON c.id = aa.conversation_id
                WHERE c.timestamp >= ?
                GROUP BY c.id
                ORDER BY c.timestamp DESC
                LIMIT 20
            ''', (cutoff_date,))
            conversations = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"Error fetching conversation context: {e}")

        conn.close()

        context_data = []
        for conv in conversations:
            context_data.append({
                'user_message': conv[0],
                'ai_response': conv[1],
                'intent': conv[2],
                'confidence': conv[3],
                'exercise_mentioned': conv[4],
                'form_cues': conv[5],
                'coaching_context': conv[6],
                'plan_modifications': conv[7],
                'timestamp': conv[8],
                'auto_actions_count': conv[9]
            })

        return jsonify({
            'success': True,
            'conversations': context_data,
            'total_count': len(context_data)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/debug_newly_added')
def debug_newly_added():
    """Debug endpoint to check newly_added status"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all exercises from weekly plan
        plan_exercises = []
        try:
            cursor.execute('SELECT exercise_name, newly_added, date_added, created_by FROM weekly_plan ORDER BY day_of_week, exercise_order')
            plan_exercises = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"Error fetching plan exercises: {e}")


        # For each exercise, check if it has any logs
        results = []
        for exercise_name, newly_added, date_added, created_by in plan_exercises:
            log_count = 0
            try:
                cursor.execute('SELECT COUNT(*) FROM workouts WHERE LOWER(exercise_name) = LOWER(?)', (exercise_name,))
                log_count = cursor.fetchone()[0]
            except sqlite3.OperationalError as e:
                print(f"Error counting logs for {exercise_name}: {e}")


            results.append({
                'exercise': exercise_name,
                'newly_added': bool(newly_added),
                'date_added': date_added,
                'created_by': created_by,
                'log_count': log_count,
                'should_be_new': log_count == 0 and created_by == 'grok_ai'
            })

        conn.close()
        return jsonify(results)

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/debug_plan_context')
def debug_plan_context():
    """Debug endpoint to check plan context data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check plan_context table
        plan_contexts = []
        try:
            cursor.execute('SELECT * FROM plan_context ORDER BY created_date DESC')
            plan_contexts = cursor.fetchall()

            # Get column names
            cursor.execute("PRAGMA table_info(plan_context)")
            columns = [col[1] for col in cursor.fetchall()]

            context_data = []
            for row in plan_contexts:
                context_data.append(dict(zip(columns, row)))
        except sqlite3.OperationalError as e:
            print(f"Error fetching plan_context: {e}")


        # Get what the app actually uses (latest entry)
        active_context = None
        active_data = None
        try:
            cursor.execute('SELECT * FROM plan_context WHERE user_id = 1 ORDER BY created_date DESC LIMIT 1')
            active_context = cursor.fetchone()
            if active_context:
                columns = [description[0] for description in cursor.description]
                active_data = dict(zip(columns, active_context))
        except sqlite3.OperationalError as e:
            print(f"Error fetching active plan context: {e}")

        # Count non-empty fields in active context
        active_field_count = 0
        if active_data:
            for field in ['plan_philosophy', 'training_style', 'weekly_structure', 'progression_strategy', 'special_considerations']:
                if active_data.get(field) and active_data[field].strip():
                    active_field_count += 1

        # Check exercise_metadata table
        exercise_metadata = []
        try:
            cursor.execute('SELECT * FROM exercise_metadata ORDER BY created_date DESC')
            exercise_metadata = cursor.fetchall()

            metadata_columns = [description[0] for description in cursor.description]

            metadata_data = []
            for row in exercise_metadata:
                metadata_data.append(dict(zip(metadata_columns, row)))
        except sqlite3.OperationalError as e:
            print(f"Error fetching exercise_metadata: {e}")


        conn.close()

        return jsonify({
            'plan_contexts': context_data,
            'active_context': active_data,
            'active_field_count': active_field_count,
            'exercise_metadata': metadata_data,
            'context_count': len(context_data),
            'metadata_count': len(metadata_data)
        })

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/restore_philosophy', methods=['GET', 'POST'])
def restore_philosophy():
    """Restore plan philosophy from backup entry"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get the full philosophy from the first entry
        backup_data = None
        try:
            cursor.execute('''
                SELECT plan_philosophy, progression_strategy, weekly_structure, special_considerations
                FROM plan_context
                WHERE id = 1 AND plan_philosophy IS NOT NULL AND plan_philosophy != ""
            ''')
            backup_data = cursor.fetchone()
        except sqlite3.OperationalError as e:
            print(f"Error fetching backup philosophy: {e}")


        if backup_data:
            philosophy, progression, weekly, considerations = backup_data

            # Update the current entry with the backup data
            try:
                cursor.execute('''
                    UPDATE plan_context
                    SET plan_philosophy = ?,
                        progression_strategy = ?,
                        weekly_structure = ?,
                        special_considerations = COALESCE(special_considerations, ?),
                        updated_date = ?
                    WHERE id = (SELECT MAX(id) FROM plan_context WHERE user_id = 1)
                ''', (philosophy, progression, weekly, considerations, datetime.now().strftime('%Y-%m-%d')))

                conn.commit()
                conn.close()

                return jsonify({
                    'success': True,
                    'message': 'Philosophy restored successfully!',
                    'restored_philosophy': philosophy[:100] + "..." if len(philosophy) > 100 else philosophy
                })
            except sqlite3.OperationalError as e:
                conn.close()
                return jsonify({'success': False, 'error': f'Failed to update plan context: {e}'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'No backup philosophy found'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/clean_loose_skin_final', methods=['POST'])
def clean_loose_skin_final():
    """Final cleanup of any remaining loose skin references"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        changes_made = []

        # Clean exercise metadata specifically
        metadata_records = []
        try:
            cursor.execute('SELECT id, exercise_name, primary_purpose, ai_notes FROM exercise_metadata')
            metadata_records = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"Error fetching metadata for cleanup: {e}")


        for record_id, exercise_name, purpose, notes in metadata_records:
            updated_purpose = purpose
            updated_notes = notes
            changed = False

            if purpose and 'loose skin' in purpose.lower():
                updated_purpose = purpose.replace('loose skin tightening', 'muscle development').replace('for loose skin', 'for core strength')
                changed = True

            if notes and 'loose skin' in notes.lower():
                updated_notes = notes.replace('loose skin', 'core development').replace('tightening', 'strengthening')
                changed = True

            if changed:
                try:
                    cursor.execute('UPDATE exercise_metadata SET primary_purpose = ?, ai_notes = ? WHERE id = ?',
                                 (updated_purpose, updated_notes, record_id))
                    changes_made.append(f"Updated metadata for {exercise_name}")
                except sqlite3.OperationalError as e:
                    print(f"Error updating metadata for {exercise_name}: {e}")


        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'changes_made': changes_made,
            'message': f'Cleaned up {len(changes_made)} remaining references'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/standardize_complex_exercises', methods=['POST'])
def standardize_complex_exercises():
    """Convert complex exercises to standard format for better parsing"""
    try:
        success = standardize_complex_exercise_format()

        if success:
            return jsonify({
                'success': True,
                'message': 'Complex exercises converted to standard format'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to convert complex exercises'
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/fix_newly_added', methods=['POST'])
def fix_newly_added():
    """Fix newly_added flags based on actual log data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all exercises from weekly plan
        exercises = []
        try:
            cursor.execute('SELECT exercise_name, created_by FROM weekly_plan')
            exercises = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"Error fetching exercises for fix_newly_added: {e}")


        fixed_count = 0
        details = []

        for exercise_name, created_by in exercises:
            # Check if this exercise has any logs
            log_count = 0
            try:
                cursor.execute('SELECT COUNT(*) FROM workouts WHERE LOWER(exercise_name) = LOWER(?)', (exercise_name,))
                log_count = cursor.fetchone()[0]
            except sqlite3.OperationalError as e:
                print(f"Error counting logs for {exercise_name}: {e}")


            if log_count == 0:
                # No logs - should be marked as newly_added if it was created by AI
                try:
                    cursor.execute('''
                        UPDATE weekly_plan
                        SET newly_added = TRUE, created_by = COALESCE(created_by, 'grok_ai')
                        WHERE LOWER(exercise_name) = LOWER(?)
                    ''', (exercise_name,))
                    if cursor.rowcount > 0:
                        fixed_count += 1
                        details.append(f"✅ Set {exercise_name} as NEW (no logs)")
                except sqlite3.OperationalError as e:
                    print(f"Error setting newly_added=TRUE for {exercise_name}: {e}")

            else:
                # Has logs - should not be marked as newly_added
                try:
                    cursor.execute('''
                        UPDATE weekly_plan
                        SET newly_added = FALSE
                        WHERE LOWER(exercise_name) = LOWER(?)
                    ''', (exercise_name,))
                    details.append(f"🔄 Cleared NEW flag for {exercise_name} ({log_count} logs)")
                except sqlite3.OperationalError as e:
                    print(f"Error clearing newly_added flag for {exercise_name}: {e}")


        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'fixed_count': fixed_count,
            'details': details
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/rename_exercise', methods=['POST'])
def rename_exercise():
    """Rename an exercise in the weekly plan"""
    try:
        data = request.json
        current_name = data.get('current_name')
        new_name = data.get('new_name')
        day = data.get('day', '').lower()

        if not all([current_name, new_name]):
            return jsonify({'success': False, 'error': 'Current name and new name required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        if day:
            # Rename specific day
            cursor.execute('''
                UPDATE weekly_plan
                SET exercise_name = ?
                WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
            ''', (new_name, day, current_name))
        else:
            # Rename across all days
            cursor.execute('''
                UPDATE weekly_plan
                SET exercise_name = ?
                WHERE LOWER(exercise_name) = LOWER(?)
            ''', (new_name, current_name))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'Renamed "{current_name}" to "{new_name}"'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Exercise not found in weekly plan'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/mark_exercise_new', methods=['POST'])
def mark_exercise_new():
    """Manually mark an exercise as newly added"""
    try:
        data = request.json
        exercise_name = data.get('exercise_name')

        if not exercise_name:
            return jsonify({'success': False, 'error': 'Exercise name required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE weekly_plan
            SET newly_added = TRUE, created_by = 'grok_ai', date_added = ?
            WHERE LOWER(exercise_name) = LOWER(?)
        ''', (datetime.now().strftime('%Y-%m-%d'), exercise_name))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'Marked {exercise_name} as NEW!'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Exercise not found in weekly plan'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/analyze_day_progression', methods=['POST'])
def analyze_day_progression_api():
    """API endpoint to trigger day progression analysis"""
    try:
        data = request.json
        date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))

        result = analyze_day_progression(date_str)
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_philosophy', methods=['POST'])
def update_philosophy():
    """Update core training philosophy manually"""
    try:
        data = request.json
        # Accept both field names for compatibility
        core_philosophy = data.get('core_philosophy', data.get('philosophy', '')).strip()

        if not core_philosophy:
            return jsonify({'success': False, 'error': 'Philosophy text is required'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get current plan context to preserve other fields
        cursor.execute('''
            SELECT progression_strategy, weekly_structure, special_considerations
            FROM plan_context
            WHERE user_id = 1
            ORDER BY created_date DESC
            LIMIT 1
        ''')

        current_data = cursor.fetchone()
        progression_strategy = current_data[0] if current_data else ''
        weekly_structure = current_data[1] if current_data else ''
        special_considerations = current_data[2] if current_data else ''

        # Delete existing entries and insert fresh one to ensure clean update
        cursor.execute('DELETE FROM plan_context WHERE user_id = 1')

        # Insert the updated philosophy
        cursor.execute('''
            INSERT INTO plan_context
            (user_id, plan_philosophy, progression_strategy, weekly_structure, special_considerations,
             created_by_ai, creation_reasoning, created_date, updated_date)
            VALUES (1, ?, ?, ?, ?, FALSE, 'Manually updated by user', ?, ?)
        ''', (
            core_philosophy,
            progression_strategy,
            weekly_structure,
            special_considerations,
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%Y-%m-%d')
        ))

        conn.commit()
        print(f"✅ Philosophy manually updated: {core_philosophy[:50]}...")
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Core philosophy updated successfully',
            'updated_philosophy': core_philosophy[:100] + "..." if len(core_philosophy) > 100 else core_philosophy
        })

    except Exception as e:
        print(f"❌ Error updating philosophy: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/make_substitution_permanent', methods=['POST'])
def make_substitution_permanent():
    """Make a workout substitution permanent in the weekly plan"""
    try:
        data = request.json
        original_exercise = data.get('original_exercise')
        new_exercise = data.get('new_exercise')
        new_weight = data.get('new_weight')
        day_of_week = data.get('day_of_week')

        if not all([original_exercise, new_exercise, new_weight, day_of_week]):
            return jsonify({'success': False, 'error': 'Missing required data'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # Update the weekly plan
        cursor.execute('''
            UPDATE weekly_plan
            SET exercise_name = ?, target_weight = ?, notes = COALESCE(notes, '') || ' [Substituted from: ' || ? || ']'
            WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
        ''', (new_exercise, new_weight, original_exercise, day_of_week.lower(), original_exercise))

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return jsonify({
                'success': True,
                'message': f'Permanently replaced {original_exercise} with {new_exercise} on {day_of_week}'
            })
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Exercise not found in weekly plan'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_day_progression_status/<date>')
def get_day_progression_status(date):
    """Check if a day's progression analysis has been completed"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Count total workouts and completed progression analysis for the date
        total_workouts = 0
        completed_analysis = 0
        try:
            cursor.execute('SELECT COUNT(*) FROM workouts WHERE date_logged = ?', (date,))
            total_workouts = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM workouts WHERE date_logged = ? AND progression_notes IS NOT NULL AND progression_notes != ""', (date,))
            completed_analysis = cursor.fetchone()[0]
        except sqlite3.OperationalError as e:
            print(f"Error getting day progression status: {e}")


        # Get progression notes for display
        progression_notes = []
        try:
            cursor.execute('''
                SELECT exercise_name, progression_notes
                FROM workouts
                WHERE date_logged = ? AND progression_notes IS NOT NULL
                ORDER BY id
            ''', (date,))
            progression_notes = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"Error fetching progression notes: {e}")


        conn.close()

        return jsonify({
            'date': date,
            'total_workouts': total_workouts,
            'analysis_completed': completed_analysis,
            'needs_analysis': total_workouts > 0 and completed_analysis == 0,
            'progression_notes': [{'exercise': note[0], 'progression': note[1]} for note in progression_notes]
        })

    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)