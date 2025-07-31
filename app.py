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
    """Get a database connection with proper timeout"""
    return sqlite3.connect('workout_logs.db', timeout=10.0)

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
        gym_location TEXT
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
        ('date_added', 'TEXT')
    ]

    # Add context columns to workouts table
    workout_columns_to_add = [
        ('substitution_reason', 'TEXT'),
        ('performance_context', 'TEXT'),
        ('environmental_factors', 'TEXT'),
        ('difficulty_rating', 'INTEGER'),
        ('gym_location', 'TEXT')
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

    cursor.execute('INSERT OR IGNORE INTO users (id, goal, weekly_split, preferences) VALUES (1, "", "", "")')

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

    # Live workout coaching
    live_workout_keywords = ['currently doing', 'doing now', 'at the gym', 'mid workout', 'between sets', 'just finished', 'form check']
    live_score = sum(1 for word in live_workout_keywords if word in prompt_lower)
    if live_score > 0:
        intents['live_workout'] = min(live_score * 0.4, 1.0)

    # Workout logging intent
    log_keywords = ['did', 'completed', 'finished', 'logged', 'performed', 'x', 'sets', 'reps', '@']
    log_patterns = [r'\d+x\d+', r'\d+\s*sets?', r'\d+\s*reps?', r'@\s*\d+']
    log_score = sum(1 for word in log_keywords if word in prompt_lower)
    log_score += sum(1 for pattern in log_patterns if re.search(pattern, prompt_lower))
    if log_score > 0:
        intents['workout_logging'] = min(log_score * 0.3, 1.0)

    # Plan modification intent
    plan_keywords = ['change', 'modify', 'update', 'add', 'remove', 'swap', 'substitute', 'replace', 'adjust', 'tweak', 'switch']
    plan_score = sum(1 for word in plan_keywords if word in prompt_lower)

    # Boost score if day mentioned or context suggests plan modification
    if any(day in prompt_lower for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
        plan_score += 2
    if any(phrase in prompt_lower for phrase in ['my plan', 'weekly plan', 'workout plan', 'current plan']):
        plan_score += 1
    if any(phrase in prompt_lower for phrase in ['can you', 'could you', 'would you', 'please']):
        plan_score += 1

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

    # Historical queries
    historical_keywords = ['did', 'last', 'history', 'previous', 'ago', 'yesterday', 'week']
    hist_score = sum(1 for word in historical_keywords if word in prompt_lower)
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
        exercise_match = None
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

def parse_plan_modification_from_ai_response(ai_response, user_request):
    """Parse Grok's response to extract specific plan modifications"""
    try:
        # Look for patterns indicating Grok wants to make changes
        response_lower = ai_response.lower()

        if not any(phrase in response_lower for phrase in ['can make', 'i can', 'absolutely', 'change', 'modify', 'update']):
            return None

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

def parse_philosophy_update_from_conversation(ai_response, user_request):
    """Parse conversation to detect philosophy/approach changes"""
    try:
        combined_text = f"{user_request} {ai_response}".lower()
        user_request_lower = user_request.lower()
        ai_response_lower = ai_response.lower()

        # Look for user requests that are asking for changes (but not just asking questions)
        user_change_requests = [
            'update my philosophy',
            'change my approach',
            'modify my philosophy',
            'tweak my philosophy',
            'revise my approach',
            'adjust my philosophy',
            'new philosophy',
            'different approach',
            'remove any mention of',
            'remove from my philosophy',
            'rewrite my philosophy'
        ]

        user_wants_change = any(request in user_request_lower for request in user_change_requests)

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

                # Create a comprehensive rewrite prompt for Grok
                rewrite_prompt = f"""Here is my current training philosophy:

CURRENT PHILOSOPHY:
Training Philosophy: {current_philosophy or 'Not set'}
Weekly Structure: {weekly_structure or 'Not set'}
Progression Strategy: {progression_strategy or 'Not set'}
Special Considerations: {special_considerations or 'Not set'}

USER REQUEST: {user_request}

Please provide a complete updated philosophy that addresses the user's request. Format your response with these exact sections:

TRAINING_PHILOSOPHY: [updated philosophy text]
WEEKLY_STRUCTURE: [updated weekly structure reasoning]
PROGRESSION_STRATEGY: [updated progression approach]
SPECIAL_CONSIDERATIONS: [updated special considerations]
PLAN_PRIORITIES: [key priorities to focus on]

Make sure to provide complete, updated versions of all sections, not just acknowledgments."""

                # Get Grok's structured rewrite
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")

                    response = client.chat.completions.create(
                        model="grok-4-0709",
                        messages=[
                            {"role": "system", "content": "You are updating a user's training philosophy. Provide complete, structured sections as requested."},
                            {"role": "user", "content": rewrite_prompt}
                        ],
                        temperature=0.7
                    )

                    grok_rewrite = response.choices[0].message.content

                    # Parse Grok's structured response
                    lines = grok_rewrite.split('\n')
                    extracted_data = {}

                    for line in lines:
                        line = line.strip()
                        if 'TRAINING_PHILOSOPHY:' in line:
                            extracted_data['plan_philosophy'] = line.split(':', 1)[1].strip() if ':' in line else ''
                        elif 'WEEKLY_STRUCTURE:' in line:
                            extracted_data['weekly_structure'] = line.split(':', 1)[1].strip() if ':' in line else ''
                        elif 'PROGRESSION_STRATEGY:' in line:
                            extracted_data['progression_strategy'] = line.split(':', 1)[1].strip() if ':' in line else ''
                        elif 'SPECIAL_CONSIDERATIONS:' in line:
                            extracted_data['special_considerations'] = line.split(':', 1)[1].strip() if ':' in line else ''
                        elif 'PLAN_PRIORITIES:' in line:
                            extracted_data['plan_priorities'] = line.split(':', 1)[1].strip() if ':' in line else ''

                    # Add reasoning
                    extracted_data['reasoning'] = f"Updated philosophy based on user request: {user_request[:100]}..."

                    print(f"🧠 Successfully rewrote philosophy with current context")
                    return extracted_data

                except Exception as e:
                    print(f"⚠️ Failed to get Grok rewrite: {str(e)}")
                    return None

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
            # Manually extract the plan priorities from the ChatGPT format
            priorities_match = re.search(r'Plan Priorities:\s*(.*)', user_request, re.DOTALL)
            priorities_text = priorities_match.group(1).strip() if priorities_match else None

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

                # If we didn't find structured sections, try to extract from natural language
                if not philosophy_sections:
                    philosophy_sections['plan_philosophy'] = ai_response.strip()

                # Extract priorities from user message if present
                if priorities_text:
                    philosophy_sections['plan_priorities'] = priorities_text
                elif "improving midsection density" in user_request_lower:
                    # Extract from the specific ChatGPT message format
                    philosophy_sections['plan_priorities'] = "Improving midsection density, building glutes, improving chest shape, adding shoulder width and arm fullness, ensuring sustainable injury-free progression"

                # Add reasoning
                philosophy_sections['reasoning'] = f"Updated based on user request: {user_request[:100]}..."

                print(f"🧠 Detected philosophy update request with substantial AI content")
                return philosophy_sections

        # No philosophy update detected
        return None

    except Exception as e:
        print(f"Error parsing philosophy update: {e}")

    return None

def regenerate_exercise_metadata_from_plan():
    """Regenerate exercise metadata when plan changes significantly"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Clear existing exercise metadata
        cursor.execute('DELETE FROM exercise_metadata WHERE user_id = 1')

        # Get all exercises from current weekly plan
        cursor.execute('''
            SELECT DISTINCT exercise_name FROM weekly_plan 
            ORDER BY exercise_name
        ''')
        exercises = cursor.fetchall()

        for (exercise_name,) in exercises:
            exercise_lower = exercise_name.lower()

            # Determine purpose and progression based on exercise type
            if any(word in exercise_lower for word in ['ab', 'crunch', 'core', 'woodchop', 'back extension']):
                purpose = "Midsection hypertrophy for loose skin tightening"
                progression_logic = "aggressive"
                notes = "Core work treated as main lift per plan philosophy"
            elif any(word in exercise_lower for word in ['press', 'chest supported row', 'glute drive', 'leg press', 'pull', 'squat', 'deadlift']):
                purpose = "Compound strength and mass building"
                progression_logic = "aggressive"
                notes = "Main compound movement"
            elif any(word in exercise_lower for word in ['leg curl', 'leg extension', 'glute slide', 'adductor']):
                purpose = "Lower body isolation and hypertrophy"
                progression_logic = "aggressive"
                notes = "Machine-based isolation for joint safety"
            elif any(word in exercise_lower for word in ['curl', 'raise', 'fly', 'lateral', 'rear delt']):
                purpose = "Upper body isolation hypertrophy"
                progression_logic = "slow"
                notes = "Isolation exercise for targeted growth"
            elif any(word in exercise_lower for word in ['pushup', 'hanging leg', 'split squat', 'goblet']):
                purpose = "Bodyweight strength and control"
                progression_logic = "slow"
                notes = "Bodyweight progression: reps → tempo → weight"
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

        conn.commit()
        conn.close()
        print(f"✅ Regenerated metadata for {len(exercises)} exercises")

    except Exception as e:
        print(f"⚠️ Error regenerating exercise metadata: {str(e)}")

def parse_preference_updates_from_conversation(ai_response, user_request):
    """Parse conversation to detect AI preference changes"""
    try:
        combined_text = f"{user_request} {ai_response}".lower()

        # Look for preference change requests
        preference_changes = {}

        # Tone preferences
        if any(phrase in combined_text for phrase in ['too long', 'shorter', 'more brief', 'less verbose', 'keep it short']):
            preference_changes['grok_detail_level'] = 'brief'
        elif any(phrase in combined_text for phrase in ['more detail', 'longer', 'more comprehensive', 'explain more']):
            preference_changes['grok_detail_level'] = 'detailed'
        elif any(phrase in combined_text for phrase in ['more casual', 'less formal', 'relaxed']):
            preference_changes['grok_tone'] = 'casual'
        elif any(phrase in combined_text for phrase in ['more professional', 'formal', 'business like']):
            preference_changes['grok_tone'] = 'professional'
        elif any(phrase in combined_text for phrase in ['more motivational', 'pump me up', 'encourage me']):
            preference_changes['grok_tone'] = 'motivational'
        elif any(phrase in combined_text for phrase in ['more analytical', 'technical', 'data focused']):
            preference_changes['grok_tone'] = 'analytical'

        # Format preferences
        if any(phrase in combined_text for phrase in ['bullet points', 'bulleted list', 'use bullets']):
            preference_changes['grok_format'] = 'bullet_points'
        elif any(phrase in combined_text for phrase in ['paragraph', 'full sentences', 'narrative']):
            preference_changes['grok_format'] = 'paragraphs'
        elif any(phrase in combined_text for phrase in ['numbered list', 'numbers', 'step by step']):
            preference_changes['grok_format'] = 'numbered_lists'

        # Communication style
        if any(phrase in combined_text for phrase in ['more direct', 'straight to the point', 'no fluff']):
            preference_changes['communication_style'] = 'direct'
        elif any(phrase in combined_text for phrase in ['more friendly', 'warmer', 'nicer']):
            preference_changes['communication_style'] = 'friendly'
        elif any(phrase in combined_text for phrase in ['more encouraging', 'supportive', 'positive']):
            preference_changes['communication_style'] = 'encouraging'

        return preference_changes if preference_changes else None

    except Exception as e:
        print(f"Error parsing preference updates: {e}")

    return None

def get_conversation_context(days_back=14, limit=10):
    """Get recent conversation context for enhanced AI responses"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get conversations from last N days
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        cursor.execute('''
            SELECT user_message, ai_response, detected_intent, exercise_mentioned, 
                   form_cues_given, performance_notes, timestamp
            FROM conversations 
            WHERE timestamp >= ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (cutoff_date, limit))

        conversations = cursor.fetchall()
        conn.close()

        if not conversations:
            return ""

        context = "\n=== RECENT CONVERSATION CONTEXT ===\n"
        for conv in reversed(conversations):  # Show oldest first for chronological context
            user_msg, ai_resp, intent, exercise, form_cues, perf_notes, timestamp = conv
            context += f"[{timestamp}] User: {user_msg[:100]}{'...' if len(user_msg) > 100 else ''}\n"
            if form_cues:
                context += f"  Form tips given: {form_cues}\n"
            if perf_notes:
                context += f"  Performance noted: {perf_notes}\n"
            context += f"  AI: {ai_resp[:150]}{'...' if len(ai_resp) > 150 else ''}\n\n"

        return context

    except Exception as e:
        print(f"Error getting conversation context: {str(e)}")
        return ""

def resolve_contextual_references(prompt, entities, conversation_context):
    """Resolve pronouns and references using conversation context"""
    if not entities.get('references') or not conversation_context:
        return prompt, {}

    resolved_entities = {}

    # Get last conversation for context
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT user_message, ai_response, exercise_mentioned, plan_modifications
        FROM conversations 
        ORDER BY timestamp DESC 
        LIMIT 3
    ''')

    recent_convs = cursor.fetchall()
    conn.close()

    if not recent_convs:
        return prompt, resolved_entities

    # Try to resolve "it", "that", "the exercise" etc.
    for conv in recent_convs:
        user_msg, ai_resp, exercise_mentioned, plan_mods = conv

        # If previous conversation mentioned a specific exercise
        if exercise_mentioned:
            resolved_entities['exercise'] = exercise_mentioned
            # Replace references in prompt
            prompt = prompt.replace(' it ', f' {exercise_mentioned} ')
            prompt = prompt.replace(' that ', f' {exercise_mentioned} ')
            break

        # If AI response mentioned specific exercises
        if ai_resp:
            import re
            exercise_pattern = r'(tricep extension|bicep curl|bench press|squat|deadlift|overhead press|lat pulldown|chest press|leg press)'
            exercise_match = re.search(exercise_pattern, ai_resp.lower())
            if exercise_match:
                resolved_entities['exercise'] = exercise_match.group(1)
                prompt = prompt.replace(' it ', f' {exercise_match.group(1)} ')
                prompt = prompt.replace(' that ', f' {exercise_match.group(1)} ')
                break

    return prompt, resolved_entities

def get_conversation_state():
    """Get current conversation state for context-aware responses"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get last conversation
        cursor.execute('''
            SELECT detected_intent, exercise_mentioned, plan_modifications, 
                   extracted_workout_data, timestamp
            FROM conversations 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''')

        last_conv = cursor.fetchone()
        conn.close()

        if not last_conv:
            return None

        return {
            'last_intent': last_conv[0],
            'last_exercise': last_conv[1],
            'last_plan_mods': last_conv[2],
            'last_workout_data': last_conv[3],
            'timestamp': last_conv[4]
        }

    except Exception as e:
        print(f"Error getting conversation state: {e}")
        return None

def build_smart_context(prompt, query_intent, user_background=None):
    """Build context based on query intent to avoid overwhelming Grok"""
    context_info = ""

    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()

    # Add conversation context for better continuity
    conversation_context = get_conversation_context()
    if conversation_context:
        context_info += conversation_context

    # Always include basic user info if available
    if user_background:
        if user_background.get('primary_goal'):
            context_info += f"User's Goal: {user_background['primary_goal']}\n"
        if user_background.get('fitness_level'):
            context_info += f"Fitness Level: {user_background['fitness_level']}\n"

    if query_intent == 'full_plan_review':
        # Provide EVERYTHING for comprehensive analysis
        context_info += "\n=== COMPLETE PLAN ANALYSIS CONTEXT ===\n"

        # User background and goals
        if user_background:
            context_info += "USER PROFILE:\n"
            if user_background.get('primary_goal'):
                context_info += f"Primary Goal: {user_background['primary_goal']}\n"
            if user_background.get('fitness_level'):
                context_info += f"Fitness Level: {user_background['fitness_level']}\n"
            if user_background.get('years_training'):
                context_info += f"Training Experience: {user_background['years_training']} years\n"
            if user_background.get('injuries_history'):
                context_info += f"Injury History: {user_background['injuries_history']}\n"
            if user_background.get('training_frequency'):
                context_info += f"Training Frequency: {user_background['training_frequency']}\n"

        # Current weekly plan with full structure
        cursor.execute('SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order FROM weekly_plan ORDER BY day_of_week, exercise_order')
        planned_exercises = cursor.fetchall()
        if planned_exercises:
            context_info += "\nCURRENT WEEKLY PLAN:\n"
            current_day = ""
            for day, exercise, sets, reps, weight, order in planned_exercises:
                if day != current_day:
                    context_info += f"\n{day.upper()}:\n"
                    current_day = day
                context_info += f"  {order}. {exercise}: {sets}x{reps}@{weight}\n"

        # Plan philosophy and context
        cursor.execute('SELECT plan_philosophy, weekly_structure, progression_strategy, special_considerations, creation_reasoning FROM plan_context WHERE user_id = 1 ORDER BY created_date DESC LIMIT 1')
        plan_context_result = cursor.fetchone()
        if plan_context_result:
            philosophy, weekly_structure, progression_strategy, special_considerations, reasoning = plan_context_result
            context_info += "\nPLAN PHILOSOPHY & CONTEXT:\n"
            if philosophy:
                context_info += f"Training Philosophy: {philosophy}\n"
            if weekly_structure:
                context_info += f"Weekly Structure Reasoning: {weekly_structure}\n"
            if progression_strategy:
                context_info += f"Progression Strategy: {progression_strategy}\n"
            if special_considerations:
                context_info += f"Special Considerations: {special_considerations}\n"
            if reasoning:
                context_info += f"Original Plan Reasoning: {reasoning[:300]}...\n"

        # Exercise-specific context
        cursor.execute('SELECT exercise_name, primary_purpose, progression_logic, ai_notes FROM exercise_metadata WHERE user_id = 1 ORDER BY exercise_name')
        exercise_metadata = cursor.fetchall()
        if exercise_metadata:
            context_info += "\nEXERCISE-SPECIFIC CONTEXT:\n"
            for exercise, purpose, progression, notes in exercise_metadata:
                context_info += f"• {exercise}: {purpose} (progression: {progression})"
                if notes:
                    context_info += f" - {notes}"
                context_info += "\n"

        # Recent performance history (last 3 weeks)
        cursor.execute("""
            SELECT exercise_name, sets, reps, weight, date_logged, notes, substitution_reason
            FROM workouts 
            WHERE date_logged >= date('now', '-21 days')
            ORDER BY date_logged DESC
            LIMIT 30
        """)
        recent_logs = cursor.fetchall()
        if recent_logs:
            context_info += "\nRECENT PERFORMANCE HISTORY (Last 3 weeks):\n"
            for log in recent_logs:
                exercise, sets, reps, weight, date, notes, sub_reason = log
                context_info += f"• {date}: {exercise} {sets}x{reps}@{weight}"
                if sub_reason:
                    context_info += f" [SUBSTITUTED: {sub_reason}]"
                if notes:
                    context_info += f" - {notes}"
                context_info += "\n"

        # Add complete weekly plan for context with proper formatting
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
        weekly_plan = cursor.fetchall()
        if weekly_plan:
            context_info += "\n\n=== CURRENT WEEKLY PLAN (ACCURATE DATA) ===\n"
            current_day = ""
            for row in weekly_plan:
                day, exercise, sets, reps, weight, order = row
                if day != current_day:
                    if current_day:  # Add newline after previous day
                        context_info += "\n"
                    context_info += f"\n{day.upper()}:\n"
                    current_day = day
                context_info += f"  {order}. {exercise}: {sets}x{reps}@{weight}\n"
            context_info += "\nIMPORTANT: Use ONLY the exercises listed above. Do not invent or add exercises that are not in this plan.\n"

        # Strip the trigger phrase from the actual prompt
        prompt = prompt.replace('FULL_PLAN_REVIEW_REQUEST:', '').strip()

    elif query_intent == 'progression':
        # Include recent performance and related exercises
        context_info += "\n=== PROGRESSION CONTEXT ===\n"

        # Get recent workouts for trend analysis
        cursor.execute("""
            SELECT exercise_name, sets, reps, weight, date_logged, substitution_reason, performance_context
            FROM workouts 
            WHERE date_logged >= date('now', '-14 days')
            ORDER BY exercise_name, date_logged DESC
        """)
        recent_logs = cursor.fetchall()

        if recent_logs:
            context_info += "Recent Performance (last 2 weeks):\n"
            for log in recent_logs[:15]:  # Limit to most relevant
                exercise, sets, reps, weight, date, sub_reason, perf_context = log
                context_info += f"• {exercise}: {sets}x{reps}@{weight} ({date})"
                if sub_reason:
                    context_info += f" - Substituted: {sub_reason}"
                if perf_context:
                    context_info += f" - {perf_context}"
                context_info += "\n"

        # Include current weekly plan with context
        cursor.execute('SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight FROM weekly_plan ORDER BY exercise_name')
        planned_exercises = cursor.fetchall()
        if planned_exercises:
            context_info += "\nCurrent Weekly Plan:\n"
            for day, exercise, sets, reps, weight in planned_exercises:
                context_info += f"• {exercise}: {sets}x{reps}@{weight} ({day})\n"

        # Include plan philosophy and reasoning
        cursor.execute('SELECT plan_philosophy, progression_strategy FROM plan_context WHERE user_id = 1 ORDER BY created_date DESC LIMIT 1')
        plan_context_result = cursor.fetchone()
        if plan_context_result:
            philosophy, progression_strategy = plan_context_result
            if philosophy:
                context_info += f"\nPlan Philosophy: {philosophy}\n"
            if progression_strategy:
                context_info += f"Progression Strategy: {progression_strategy}\n"

    elif query_intent == 'exercise_specific':
        # Find the specific exercise mentioned and get its history
        context_info += "\n=== EXERCISE-SPECIFIC CONTEXT ===\n"

        # Extract exercise name from prompt (simple approach)
        exercise_keywords = ['bench', 'squat', 'deadlift', 'press', 'curl', 'row', 'pull']
        mentioned_exercise = None
        for keyword in exercise_keywords:
            if keyword in prompt.lower():
                mentioned_exercise = keyword
                break

        if mentioned_exercise:
            # Get history for this exercise and related ones
            cursor.execute("""
                SELECT exercise_name, sets, reps, weight, date_logged, substitution_reason, performance_context
                FROM workouts 
                WHERE LOWER(exercise_name) LIKE ?
                ORDER BY date_logged DESC
                LIMIT 10
            """, (f'%{mentioned_exercise}%',))

            exercise_history = cursor.fetchall()
            if exercise_history:
                context_info += f"Recent {mentioned_exercise} history:\n"
                for log in exercise_history:
                    exercise, sets, reps, weight, date, sub_reason, perf_context = log
                    context_info += f"• {date}: {sets}x{reps}@{weight}"
                    if sub_reason:
                        context_info += f" (sub: {sub_reason})"
                    if perf_context:
                        context_info += f" - {perf_context}"
                    context_info += "\n"

    elif query_intent == 'historical':
        # Include recent workout summary
        context_info += "\n=== RECENT HISTORY ===\n"
        cursor.execute("""
            SELECT exercise_name, sets, reps, weight, date_logged, notes, substitution_reason
            FROM workouts 
            ORDER BY date_logged DESC 
            LIMIT 20
        """)
        recent_logs = cursor.fetchall()
        if recent_logs:
            context_info += "Recent workouts:\n"
            for w in recent_logs[:10]:
                context_info += f"• {w[0]}: {w[1]}x{w[2]}@{w[3]} ({w[4]})"
                if w[6]:  # substitution_reason
                    context_info += f" [SUBSTITUTED: {w[6]}]"
                context_info += "\n"

        # Include weekly plan for comparison
        cursor.execute('SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight FROM weekly_plan ORDER BY day_of_week')
        planned_exercises = cursor.fetchall()
        if planned_exercises:
            context_info += "\nWeekly Plan for Reference:\n"
            current_day = ""
            for day, exercise, sets, reps, weight in planned_exercises:
                if day != current_day:
                    context_info += f"\n{day.title()}:\n"
                    current_day = day
                context_info += f"  • {exercise}: {sets}x{reps}@{weight}\n"

    elif query_intent == 'general':
        # Minimal context for general chat
        context_info += "\n=== BASIC INFO ===\n"
        cursor.execute('SELECT COUNT(*) FROM workouts WHERE date_logged >= date("now", "-7 days")')
        recent_count = cursor.fetchone()[0]
        context_info += f"Workouts this week: {recent_count}\n"

    conn.close()
    return context_info

def get_grok_response_with_context(prompt, user_background=None, recent_workouts=None):
    """Context-aware Grok response with smart context selection"""
    try:
        client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")

        # Analyze query intent and build appropriate context
        query_intent = analyze_query_intent(prompt)
        context_info = build_smart_context(prompt, query_intent, user_background)

        # Build final prompt with smart context
        full_prompt = context_info + "\n\n" + prompt

        # Adjust system prompt based on query type
        if query_intent == 'full_plan_review':
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
            system_prompt = """You are Grok, an AI assistant with access to the user's workout history and fitness profile. 

🤖 IMPORTANT: You have the ability to modify the user's weekly workout plan directly! When they ask for plan changes, you can actually make them happen.

PLAN MODIFICATION CAPABILITIES:
- When user asks to modify their plan (change exercises, sets, reps, weight), respond with enthusiasm: "Absolutely! I can add that to your plan."
- Briefly explain what you'll add and why it's a good choice
- Be specific about the exercise details: "I'll add Roman Chair Back Extensions with a 45lb plate to your Wednesday routine - 3 sets of 8-12 reps."
- End with: "I'll add this to your plan now." (Don't ask for permission again if they've already confirmed)
- When they say "yes" or "yes please" to a plan change, that means they want you to proceed
- The system will automatically show them a confirmation button to actually execute the change

RESPONSE LENGTH GUIDELINES:
- Greetings ("hello", "hi", "hey"): Respond naturally like a normal conversation - "Hey! What's up?" or "Hello!" Don't mention workouts unless they ask about fitness
- General questions ("what can you do"): Moderate length with bullet points
- Historical data ("what did I do Friday"): Brief summary format
- Plan modifications: Be enthusiastic and specific about what you can change
- Progression tips: Use this specific format:
  • Exercise Name: specific actionable change (e.g., "bump up to 40 lbs", "go for 25 reps")
  • Exercise Name: specific actionable change
  Then end with: "Ask for my reasoning on any of these progressions if you'd like more detail."

GREETING BEHAVIOR:
- For simple greetings (hello, hi, hey, what's up), respond like a normal person would
- Don't immediately jump into fitness talk unless they ask about fitness
- Be casual and friendly - you're having a conversation, not giving a sales pitch
- Examples: "Hey!" "What's going on?" "Hi there!" "Hello! How's it going?"

CONTEXT USAGE:
- Only reference workout data when the question actually requires it
- For greetings and casual conversation, respond naturally without mentioning workout data
- For specific fitness questions, use the provided context appropriately
- Don't feel obligated to reference every piece of context data you have access to

STYLE: Be direct and cut unnecessary filler words. Get straight to the point while staying helpful. Avoid introductory phrases like "Great question!" or "Here's what I think" - just dive into the answer."""

        response = client.chat.completions.create(
            model="grok-4-0709",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
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
    cursor.execute('SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, COALESCE(notes, ""), COALESCE(newly_added, 0) FROM weekly_plan WHERE day_of_week = ? ORDER BY exercise_order', (today_lowercase,))
    plan_data = cursor.fetchall()

    # Check completion status for each exercise
    today_plan = []
    for row in plan_data:
        exercise_id, day, exercise_name, target_sets, target_reps, target_weight, order, notes, newly_added = row

        # Check if this exercise was logged today
        cursor.execute('''
            SELECT sets, reps, weight, notes 
            FROM workouts 
            WHERE LOWER(exercise_name) = LOWER(?) AND date_logged = ?
            ORDER BY id DESC LIMIT 1
        ''', (exercise_name, today_date))

        logged_workout = cursor.fetchone()

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
            except:
                completion_status['status_text'] = 'Completed'
                completion_status['status_class'] = 'text-success'

        # Add completion status and newly_added flag to the row data
        today_plan.append((*row[:-1], completion_status, bool(newly_added)))

    # Calculate stats
    from collections import namedtuple
    Stats = namedtuple('Stats', ['week_volume', 'month_volume', 'week_workouts', 'latest_weight', 'weight_date'])

    # Week volume - handle non-numeric weight values
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    cursor.execute('SELECT exercise_name, sets, reps, weight FROM workouts WHERE date_logged >= ?', (week_ago,))
    week_workouts_data = cursor.fetchall()

    week_volume = 0
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

    # Month volume - handle non-numeric weight values
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    cursor.execute('SELECT exercise_name, sets, reps, weight FROM workouts WHERE date_logged >= ?', (month_ago,))
    month_workouts_data = cursor.fetchall()

    month_volume = 0
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

    # Week workouts count
    cursor.execute('SELECT COUNT(DISTINCT date_logged) FROM workouts WHERE date_logged >= ?', (week_ago,))
    week_workouts = cursor.fetchone()[0] or 0

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
    cursor.execute('SELECT onboarding_completed FROM user_background WHERE user_id = 1')
    bg_result = cursor.fetchone()
    needs_onboarding = not bg_result or not bg_result[0]

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
            cursor.execute('SELECT COUNT(*) FROM user_background WHERE user_id = 1')
            if cursor.fetchone()[0] > 0:
                cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY id DESC LIMIT 1')
                user_bg = cursor.fetchone()
                if user_bg:
                    columns = [description[0] for description in cursor.description]
                    user_background = dict(zip(columns, user_bg))
                else:
                    user_background = None
            else:
                user_background = None

            # Get recent workouts for context
            cursor.execute('SELECT exercise_name, sets, reps, weight, date_logged FROM workouts ORDER BY date_logged DESC LIMIT 10')
            recent_logs = cursor.fetchall()
            recent_workouts = ""
            if recent_logs:
                recent_workouts = "Recent exercises:\n"
                for log in recent_logs[:5]:  # Limit to 5 most recent
                    recent_workouts += f"- {log[0]}: {log[1]}x{log[2]} @ {log[3]} ({log[4]})\n"

            conn.close()
            print(f"Database queries completed successfully")  # Debug log

            # Build context-aware prompt with conversation history for follow-ups
            if conv_history and len(conv_history) > 50:
                # This is a follow-up question - include recent conversation context
                context_prompt = f"PREVIOUS CONVERSATION:\n{conv_history[-1000:]}\n\nUSER'S FOLLOW-UP: {message}"
                response = get_grok_response_with_context(context_prompt, user_background, recent_workouts)
            else:
                # First message or no significant history
                response = get_grok_response_with_context(message, user_background, recent_workouts)
            print(f"AI response received: {len(response)} characters")  # Debug log

        except Exception as e:
            print(f"Error in chat_stream: {str(e)}")
            response = "Sorry, I encountered an error processing your request. Please try again."

        for word in response.split():
            yield word + " "

    return Response(generate(user_message, conversation_history), mimetype='text/plain')

@app.route('/log_workout', methods=['POST'])
def log_workout():
    data = request.get_json()
    exercise_name = data['exercise_name']
    sets = data['sets']
    reps = data['reps']
    weight = data['weight']
    notes = data.get('notes', '')
    date_logged = datetime.now().strftime('%Y-%m-%d')
    substitution_reason = data.get('substitution_reason', '')
    performance_context = data.get('performance_context', '')
    environmental_factors = data.get('environmental_factors', '')
    difficulty_rating = data.get('difficulty_rating', None)
    gym_location = data.get('gym_location', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Execute query
    cursor.execute('''
        INSERT INTO workouts 
        (exercise_name, sets, reps, weight, notes, date_logged, substitution_reason, 
         performance_context, environmental_factors, difficulty_rating, gym_location) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (exercise_name, sets, reps, weight, notes, date_logged, substitution_reason, 
          performance_context, environmental_factors, difficulty_rating, gym_location))

    # Commit changes
    conn.commit()

    # Fetch the newly inserted workout
    cursor.execute('''
        SELECT id, exercise_name, sets, reps, weight, notes, date_logged, substitution_reason, 
               performance_context, environmental_factors, difficulty_rating, gym_location
        FROM workouts
        WHERE exercise_name = ? AND date_logged = ?
        ORDER BY id DESC
        LIMIT 1
    ''', (exercise_name, date_logged))

    new_workout = cursor.fetchone()
    conn.close()

    # Convert the row to a dictionary (optional, but good practice)
    if new_workout:
        columns = [col[0] for col in cursor.description]
        workout_dict = dict(zip(columns, new_workout))
    else:
        workout_dict = None

    return jsonify({'message': 'Workout logged!', 'workout': workout_dict}), 200

@app.route('/get_all_workouts', methods=['GET'])
def get_all_workouts():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all workouts
    cursor.execute('SELECT * FROM workouts ORDER BY date_logged DESC LIMIT 100')
    workouts = cursor.fetchall()

    # Convert to list of dictionaries
    workout_list = []
    for workout in workouts:
        workout_dict = {
            'id': workout[0],
            'exercise_name': workout[1],
            'sets': workout[2],
            'reps': workout[3],
            'weight': workout[4],
            'notes': workout[5],
            'date_logged': workout[6],
            'substitution_reason': workout[7],
            'performance_context': workout[8],
            'environmental_factors': workout[9],
            'difficulty_rating': workout[10],
            'gym_location': workout[11]
        }
        workout_list.append(workout_dict)

    conn.close()
    return jsonify(workout_list), 200

@app.route('/get_exercise_history/<exercise_name>', methods=['GET'])
def get_exercise_history(exercise_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch exercise history
    cursor.execute('''
        SELECT * FROM workouts 
        WHERE LOWER(exercise_name) = LOWER(?)
        ORDER BY date_logged DESC
        LIMIT 50
    ''', (exercise_name,))

    workouts = cursor.fetchall()

    # Convert to list of dictionaries
    workout_list = []
    for workout in workouts:
        workout_dict = {
            'id': workout[0],
            'exercise_name': workout[1],
            'sets': workout[2],
            'reps': workout[3],
            'weight': workout[4],
            'notes': workout[5],
            'date_logged': workout[6],
            'substitution_reason': workout[7],
            'performance_context': workout[8],
            'environmental_factors': workout[9],
            'difficulty_rating': workout[10],
            'gym_location': workout[11]
        }
        workout_list.append(workout_dict)

    conn.close()
    return jsonify(workout_list), 200

@app.route('/get_ai_suggestions', methods=['POST'])
def get_ai_suggestions():
    data = request.get_json()
    exercise_name = data['exercise_name']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get general tips for exercise
    cursor.execute('SELECT ai_notes FROM exercise_metadata WHERE LOWER(exercise_name) = LOWER(?)', (exercise_name,))
    result = cursor.fetchone()
    ai_notes = result[0] if result else "No AI tips found for this exercise."

    # Get form cues from historical conversations
    cursor.execute('''
        SELECT DISTINCT form_cues_given
        FROM conversations
        WHERE LOWER(exercise_mentioned) = LOWER(?)
        AND form_cues_given IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 5
    ''', (exercise_name,))

    form_cues_results = cursor.fetchall()
    form_cues = [row[0] for row in form_cues_results if row[0]]

    conn.close()
    return jsonify({'ai_notes': ai_notes, 'form_cues': form_cues}), 200

@app.route('/update_workout/<int:workout_id>', methods=['PUT'])
def update_workout(workout_id):
    data = request.get_json()
    exercise_name = data['exercise_name']
    sets = data['sets']
    reps = data['reps']
    weight = data['weight']
    notes = data['notes']
    substitution_reason = data.get('substitution_reason', '')
    performance_context = data.get('performance_context', '')
    environmental_factors = data.get('environmental_factors', '')
    difficulty_rating = data.get('difficulty_rating', None)
    gym_location = data.get('gym_location', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE workouts 
        SET exercise_name = ?, sets = ?, reps = ?, weight = ?, notes = ?,
            substitution_reason = ?, performance_context = ?, environmental_factors = ?,
            difficulty_rating = ?, gym_location = ?
        WHERE id = ?
    ''', (exercise_name, sets, reps, weight, notes, substitution_reason, performance_context,
          environmental_factors, difficulty_rating, gym_location, workout_id))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Workout updated!'}), 200

@app.route('/delete_workout/<int:workout_id>', methods=['DELETE'])
def delete_workout(workout_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM workouts WHERE id = ?', (workout_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Workout deleted!'}), 200

@app.route('/get_weekly_plan', methods=['GET'])
def get_weekly_plan():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch weekly plan with proper ordering
    cursor.execute('''
        SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, newly_added
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

    # Convert to list of dictionaries
    plan_list = []
    for row in plan_data:
        exercise_id, day, exercise_name, target_sets, target_reps, target_weight, order, notes, newly_added = row
        plan_list.append({
            'id': exercise_id,
            'day_of_week': day,
            'exercise_name': exercise_name,
            'target_sets': target_sets,
            'target_reps': target_reps,
            'target_weight': target_weight,
            'exercise_order': order,
            'notes': notes,
            'newly_added': bool(newly_added)
        })

    conn.close()
    return jsonify(plan_list), 200

@app.route('/add_exercise_to_plan', methods=['POST'])
def add_exercise_to_plan():
    data = request.get_json()
    day_of_week = data['day_of_week']
    exercise_name = data['exercise_name']
    target_sets = data['target_sets']
    target_reps = data['target_reps']
    target_weight = data['target_weight']
    notes = data.get('notes', '')  # Optional notes field
    newly_added = True  # Flag as newly added

    conn = get_db_connection()
    cursor = conn.cursor()

    # Find the highest existing order index for the given day
    cursor.execute('SELECT MAX(exercise_order) FROM weekly_plan WHERE day_of_week = ?', (day_of_week,))
    max_order = cursor.fetchone()[0] or 0  # If no exercises exist, start at 1

    # Increment the order index
    exercise_order = max_order + 1

    # Get the current date
    date_added = datetime.now().strftime('%Y-%m-%d')

    # Execute query with notes and newly_added flag
    cursor.execute('''
        INSERT INTO weekly_plan 
        (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, newly_added, date_added) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, newly_added, date_added))

    # Commit changes
    conn.commit()

    # Fetch the newly inserted exercise
    cursor.execute('''
        SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, newly_added
        FROM weekly_plan 
        WHERE day_of_week = ? AND exercise_name = ?
        ORDER BY id DESC
        LIMIT 1
    ''', (day_of_week, exercise_name))

    new_exercise = cursor.fetchone()
    conn.close()

    # Convert the row to a dictionary
    if new_exercise:
        columns = [col[0] for col in cursor.description]
        exercise_dict = dict(zip(columns, new_exercise))
    else:
        exercise_dict = None

    return jsonify({'message': 'Exercise added to plan!', 'exercise': exercise_dict}), 200

@app.route('/update_exercise_in_plan/<int:exercise_id>', methods=['PUT'])
def update_exercise_in_plan(exercise_id):
    data = request.get_json()
    day_of_week = data['day_of_week']
    exercise_name = data['exercise_name']
    target_sets = data['target_sets']
    target_reps = data['target_reps']
    target_weight = data['target_weight']
    exercise_order = data['exercise_order']  # Include exercise_order
    notes = data.get('notes', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Execute query with exercise_order
    cursor.execute('''
        UPDATE weekly_plan 
        SET day_of_week = ?, exercise_name = ?, target_sets = ?, target_reps = ?, 
            target_weight = ?, exercise_order = ?, notes = ?
        WHERE id = ?
    ''', (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, exercise_id))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Exercise in plan updated!'}), 200

@app.route('/delete_exercise_from_plan/<int:exercise_id>', methods=['DELETE'])
def delete_exercise_from_plan(exercise_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM weekly_plan WHERE id = ?', (exercise_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Exercise deleted from plan!'}), 200

@app.route('/clear_newly_added_flags', methods=['POST'])
def clear_newly_added_flags():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE weekly_plan SET newly_added = 0')
    conn.commit()
    conn.close()
    return jsonify({'message': 'Newly added flags cleared!'}), 200

@app.route('/get_plan_context', methods=['GET'])
def get_plan_context():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch plan context
    cursor.execute('''
        SELECT plan_philosophy, training_style, weekly_structure, 
               progression_strategy, special_considerations
        FROM plan_context 
        WHERE user_id = 1
        ORDER BY created_date DESC
        LIMIT 1
    ''')
    context_data = cursor.fetchone()

    conn.close()

    if context_data:
        # Convert to dictionary
        context_dict = {
            'plan_philosophy': context_data[0],
            'training_style': context_data[1],
            'weekly_structure': context_data[2],
            'progression_strategy': context_data[3],
            'special_considerations': context_data[4]
        }
        return jsonify(context_dict), 200
    else:
        return jsonify({'message': 'No plan context found.'}), 404

@app.route('/update_plan_context', methods=['POST'])
def update_plan_context():
    data = request.get_json()
    plan_philosophy = data['plan_philosophy']
    training_style = data['training_style']
    weekly_structure = data['weekly_structure']
    progression_strategy = data['progression_strategy']
    special_considerations = data['special_considerations']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get current timestamp
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Insert new context data
    cursor.execute('''
        INSERT INTO plan_context 
        (user_id, plan_philosophy, training_style, weekly_structure, 
         progression_strategy, special_considerations, created_date) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (1, plan_philosophy, training_style, weekly_structure, 
          progression_strategy, special_considerations, now))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Plan context updated!'}), 200

@app.route('/get_exercise_metadata/<exercise_name>', methods=['GET'])
def get_exercise_metadata(exercise_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch metadata
    cursor.execute('''
        SELECT exercise_type, primary_purpose, progression_logic, ai_notes
        FROM exercise_metadata 
        WHERE LOWER(exercise_name) = LOWER(?)
        AND user_id = 1
    ''', (exercise_name,))
    metadata = cursor.fetchone()

    conn.close()

    if metadata:
        # Convert to dictionary
        metadata_dict = {
            'exercise_type': metadata[0],
            'primary_purpose': metadata[1],
            'progression_logic': metadata[2],
            'ai_notes': metadata[3]
        }
        return jsonify(metadata_dict), 200
    else:
        return jsonify({'message': 'No metadata found for this exercise.'}), 404

@app.route('/update_exercise_metadata/<exercise_name>', methods=['PUT'])
def update_exercise_metadata(exercise_name):
    data = request.get_json()
    exercise_type = data['exercise_type']
    primary_purpose = data['primary_purpose']
    progression_logic = data['progression_logic']
    ai_notes = data['ai_notes']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Update metadata
    cursor.execute('''
        UPDATE exercise_metadata 
        SET exercise_type = ?, primary_purpose = ?, progression_logic = ?, ai_notes = ?
        WHERE LOWER(exercise_name) = LOWER(?)
        AND user_id = 1
    ''', (exercise_type, primary_purpose, progression_logic, ai_notes, exercise_name))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Exercise metadata updated!'}), 200

@app.route('/get_user_preferences', methods=['GET'])
def get_user_preferences():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user preferences
    cursor.execute('SELECT * FROM users WHERE id = 1')
    user_data = cursor.fetchone()

    conn.close()

    if user_data:
        # Convert to dictionary
        user_dict = {
            'id': user_data[0],
            'goal': user_data[1],
            'weekly_split': user_data[2],
            'preferences': user_data[3],
            'grok_tone': user_data[4],
            'grok_detail_level': user_data[5],
            'grok_format': user_data[6],
            'preferred_units': user_data[7],
            'communication_style': user_data[8],
            'technical_level': user_data[9]
        }
        return jsonify(user_dict), 200
    else:
        return jsonify({'message': 'No user preferences found.'}), 404

@app.route('/update_user_preferences', methods=['POST'])
def update_user_preferences():
    data = request.get_json()
    goal = data['goal']
    weekly_split = data['weekly_split']
    preferences = data['preferences']
    grok_tone = data['grok_tone']
    grok_detail_level = data['grok_detail_level']
    grok_format = data['grok_format']
    preferred_units = data['preferred_units']
    communication_style = data['communication_style']
    technical_level = data['technical_level']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Update user preferences
    cursor.execute('''
        UPDATE users 
        SET goal = ?, weekly_split = ?, preferences = ?, grok_tone = ?,
            grok_detail_level = ?, grok_format = ?, preferred_units = ?,
            communication_style = ?, technical_level = ?
        WHERE id = 1
    ''', (goal, weekly_split, preferences, grok_tone, grok_detail_level,
          grok_format, preferred_units, communication_style, technical_level))

    conn.commit()
    conn.close()
    return jsonify({'message': 'User preferences updated!'}), 200

@app.route('/log_conversation', methods=['POST'])
def log_conversation():
    data = request.get_json()
    user_message = data['user_message']
    ai_response = data['ai_response']
    detected_intent = data.get('detected_intent', None)
    confidence_score = data.get('confidence_score', 0.0)
    actions_taken = data.get('actions_taken', None)
    workout_context = data.get('workout_context', None)
    exercise_mentioned = data.get('exercise_mentioned', None)
    form_cues_given = data.get('form_cues_given', None)
    performance_notes = data.get('performance_notes', None)
    plan_modifications = data.get('plan_modifications', None)
    auto_executed_actions = data.get('auto_executed_actions', None)
    extracted_workout_data = data.get('extracted_workout_data', None)
    coaching_context = data.get('coaching_context', None)
    session_id = data.get('session_id', None)
    conversation_thread_id = data.get('conversation_thread_id', None)
    parent_conversation_id = data.get('parent_conversation_id', None)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Log conversation
    cursor.execute('''
        INSERT INTO conversations 
        (user_id, user_message, ai_response, detected_intent, confidence_score,
         actions_taken, workout_context, exercise_mentioned, form_cues_given,
         performance_notes, plan_modifications, auto_executed_actions,
         extracted_workout_data, coaching_context, timestamp, session_id,
         conversation_thread_id, parent_conversation_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (1, user_message, ai_response, detected_intent, confidence_score,
          actions_taken, workout_context, exercise_mentioned, form_cues_given,
          performance_notes, plan_modifications, auto_executed_actions,
          extracted_workout_data, coaching_context, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          session_id, conversation_thread_id, parent_conversation_id))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Conversation logged!'}), 200

@app.route('/get_conversation_history', methods=['GET'])
def get_conversation_history():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch conversation history (last 50 messages)
    cursor.execute('''
        SELECT user_message, ai_response, timestamp
        FROM conversations
        ORDER BY timestamp DESC
        LIMIT 50
    ''')
    conversations = cursor.fetchall()

    conn.close()

    # Convert to list of dictionaries
    conversation_list = []
    for conv in conversations:
        conversation_list.append({
            'user_message': conv[0],
            'ai_response': conv[1],
            'timestamp': conv[2]
        })

    return jsonify(conversation_list), 200

@app.route('/get_exercise_relationships/<primary_exercise>', methods=['GET'])
def get_exercise_relationships(primary_exercise):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch relationships
    cursor.execute('''
        SELECT related_exercise, relationship_type, relevance_score
        FROM exercise_relationships
        WHERE LOWER(primary_exercise) = LOWER(?)
    ''', (primary_exercise,))
    relationships = cursor.fetchall()

    conn.close()

    # Convert to list of dictionaries
    relationship_list = []
    for rel in relationships:
        relationship_list.append({
            'related_exercise': rel[0],
            'relationship_type': rel[1],
            'relevance_score': rel[2]
        })

    return jsonify(relationship_list), 200

@app.route('/create_exercise_relationship', methods=['POST'])
def create_exercise_relationship():
    data = request.get_json()
    primary_exercise = data['primary_exercise']
    related_exercise = data['related_exercise']
    relationship_type = data['relationship_type']
    relevance_score = data.get('relevance_score', 1.0)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create relationship
    cursor.execute('''
        INSERT INTO exercise_relationships 
        (primary_exercise, related_exercise, relationship_type, relevance_score)
        VALUES (?, ?, ?, ?)
    ''', (primary_exercise, related_exercise, relationship_type, relevance_score))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Exercise relationship created!'}), 200

@app.route('/delete_exercise_relationship', methods=['DELETE'])
def delete_exercise_relationship():
    data = request.get_json()
    primary_exercise = data['primary_exercise']
    related_exercise = data['related_exercise']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Delete relationship
    cursor.execute('''
        DELETE FROM exercise_relationships
        WHERE LOWER(primary_exercise) = LOWER(?) AND LOWER(related_exercise) = LOWER(?)
    ''', (primary_exercise, related_exercise))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Exercise relationship deleted!'}), 200

@app.route('/get_user_background', methods=['GET'])
def get_user_background():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch user background
    cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY id DESC LIMIT 1')
    bg_data = cursor.fetchone()

    conn.close()

    if bg_data:
        # Get column names
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_background WHERE user_id = 1 LIMIT 1')
        columns = [description[0] for description in cursor.description]

        # Convert to dictionary
        bg_dict = dict(zip(columns, bg_data))
        return jsonify(bg_dict), 200
    else:
        return jsonify({'message': 'No user background found.'}), 404

@app.route('/update_user_background', methods=['POST'])
def update_user_background():
    data = request.get_json()

    # Extract data from request
    age = data.get('age')
    gender = data.get('gender')
    height = data.get('height')
    current_weight = data.get('current_weight')
    fitness_level = data.get('fitness_level')
    years_training = data.get('years_training')
    primary_goal = data.get('primary_goal')
    secondary_goals = data.get('secondary_goals')
    injuries_history = data.get('injuries_history')
    current_limitations = data.get('current_limitations')
    past_weight_loss = data.get('past_weight_loss')
    past_weight_gain = data.get('past_weight_gain')
    medical_conditions = data.get('medical_conditions')
    training_frequency = data.get('training_frequency')
    available_equipment = data.get('available_equipment')
    time_per_session = data.get('time_per_session')
    preferred_training_style = data.get('preferred_training_style')
    motivation_factors = data.get('motivation_factors')
    biggest_challenges = data.get('biggest_challenges')
    past_program_experience = data.get('past_program_experience')
    nutrition_approach = data.get('nutrition_approach')
    sleep_quality = data.get('sleep_quality')
    stress_level = data.get('stress_level')
    additional_notes = data.get('additional_notes')
    chat_response_style = data.get('chat_response_style')
    chat_progression_detail = data.get('chat_progression_detail')
    onboarding_completed = data.get('onboarding_completed')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get current timestamp
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Insert/Update user background
    cursor.execute('''
        INSERT INTO user_background (
            user_id, age, gender, height, current_weight, fitness_level, years_training,
            primary_goal, secondary_goals, injuries_history, current_limitations,
            past_weight_loss, past_weight_gain, medical_conditions, training_frequency,
            available_equipment, time_per_session, preferred_training_style,
            motivation_factors, biggest_challenges, past_program_experience,
            nutrition_approach, sleep_quality, stress_level, additional_notes,
            chat_response_style, chat_progression_detail, onboarding_completed,
            created_date, updated_date
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(user_id) DO UPDATE SET
            age=excluded.age, gender=excluded.gender, height=excluded.height,
            current_weight=excluded.current_weight, fitness_level=excluded.fitness_level,
            years_training=excluded.years_training, primary_goal=excluded.primary_goal,
            secondary_goals=excluded.secondary_goals, injuries_history=excluded.injuries_history,
            current_limitations=excluded.current_limitations, past_weight_loss=excluded.past_weight_loss,
            past_weight_gain=excluded.past_weight_gain, medical_conditions=excluded.medical_conditions,
            training_frequency=excluded.training_frequency, available_equipment=excluded.available_equipment,
            time_per_session=excluded.time_per_session, preferred_training_style=excluded.preferred_training_style,
            motivation_factors=excluded.motivation_factors, biggest_challenges=excluded.biggest_challenges,
            past_program_experience=excluded.past_program_experience, nutrition_approach=excluded.nutrition_approach,
            sleep_quality=excluded.sleep_quality, stress_level=excluded.stress_level,
            additional_notes=excluded.additional_notes, chat_response_style=excluded.chat_response_style,
            chat_progression_detail=excluded.chat_progression_detail, onboarding_completed=excluded.onboarding_completed,
            updated_date=?
    ''', (
        1, age, gender, height, current_weight, fitness_level, years_training,
        primary_goal, secondary_goals, injuries_history, current_limitations,
        past_weight_loss, past_weight_gain, medical_conditions, training_frequency,
        available_equipment, time_per_session, preferred_training_style,
        motivation_factors, biggest_challenges, past_program_experience,
        nutrition_approach, sleep_quality, stress_level, additional_notes,
        chat_response_style, chat_progression_detail, onboarding_completed,
        now, now
    ))

    conn.commit()
    conn.close()
    return jsonify({'message': 'User background updated!'}), 200

@app.route('/create_conversation_thread', methods=['POST'])
def create_conversation_thread():
    data = request.get_json()
    thread_type = data.get('thread_type', 'chat')
    thread_subject = data.get('thread_subject', None)
    current_context = data.get('current_context', None)
    last_intent = data.get('last_intent', None)
    active_workout_session = data.get('active_workout_session', False)
    workout_session_data = data.get('workout_session_data', None)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create conversation thread
    cursor.execute('''
        INSERT INTO conversation_threads (
            user_id, thread_type, thread_subject, current_context, last_intent,
            active_workout_session, workout_session_data, created_timestamp, updated_timestamp
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    ''', (
        1, thread_type, thread_subject, current_context, last_intent,
        active_workout_session, workout_session_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))

    thread_id = cursor.lastrowid  # Get the ID of the new thread
    conn.commit()
    conn.close()
    return jsonify({'message': 'Conversation thread created!', 'thread_id': thread_id}), 200

@app.route('/get_conversation_thread/<int:thread_id>', methods=['GET'])
def get_conversation_thread(thread_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch thread
    cursor.execute('''
        SELECT * FROM conversation_threads WHERE id = ?
    ''', (thread_id,))
    thread_data = cursor.fetchone()

    conn.close()

    if thread_data:
        # Get column names
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM conversation_threads WHERE id = ? LIMIT 1', (thread_id,))
        columns = [description[0] for description in cursor.description]

        # Convert to dictionary
        thread_dict = dict(zip(columns, thread_data))
        return jsonify(thread_dict), 200
    else:
        return jsonify({'message': 'Conversation thread not found.'}), 404
@app.route('/update_conversation_thread/<int:thread_id>', methods=['PUT'])
def update_conversation_thread(thread_id):
    data = request.get_json()
    thread_type = data.get('thread_type')
    thread_subject = data.get('thread_subject')
    current_context = data.get('current_context')
    last_intent = data.get('last_intent')
    active_workout_session = data.get('active_workout_session')
    workout_session_data = data.get('workout_session_data')
    is_active = data.get('is_active')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Update thread
    cursor.execute('''
        UPDATE conversation_threads SET
            thread_type = ?, thread_subject = ?, current_context = ?, last_intent = ?,
            active_workout_session = ?, workout_session_data = ?, updated_timestamp = ?,
            is_active = ?
        WHERE id = ?
    ''', (
        thread_type, thread_subject, current_context, last_intent,
        active_workout_session, workout_session_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        is_active, thread_id
    ))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Conversation thread updated!'}), 200

@app.route('/get_conversations_in_thread/<thread_id>', methods=['GET'])
def get_conversations_in_thread(thread_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch conversations
    cursor.execute('''
        SELECT user_message, ai_response, timestamp
        FROM conversations
        WHERE conversation_thread_id = ?
        ORDER BY timestamp ASC
    ''', (thread_id,))
    conversations = cursor.fetchall()

    conn.close()

    # Convert to list of dictionaries
    conversation_list = []
    for conv in conversations:
        conversation_list.append({
            'user_message': conv[0],
            'ai_response': conv[1],
            'timestamp': conv[2]
        })

    return jsonify(conversation_list), 200

@app.route('/log_workout')
def log_workout_page():
    return render_template('log_workout.html')

@app.route('/weekly_plan')
def weekly_plan():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get weekly plan data
    cursor.execute('''
        SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, newly_added
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

    # Organize data by day
    plan_by_day = {}
    for row in plan_data:
        exercise_id, day, exercise_name, target_sets, target_reps, target_weight, order, notes, newly_added = row
        if day not in plan_by_day:
            plan_by_day[day] = []

        plan_by_day[day].append({
            'id': exercise_id,
            'exercise': exercise_name,
            'sets': target_sets,
            'reps': target_reps,
            'weight': target_weight,
            'order': order,
            'notes': notes or '',
            'newly_added': bool(newly_added)
        })

    return render_template('weekly_plan.html', plan_by_day=plan_by_day)

@app.route('/progression')
def progression():
    return render_template('progression.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/analyze_plan')
def analyze_plan():
    return render_template('analyze_plan.html')

@app.route('/save_workout', methods=['POST'])
def save_workout():
    data = request.get_json()
    exercise_name = data['exercise_name']
    sets = data['sets']
    reps = data['reps']
    weight = data['weight']
    notes = data.get('notes', '')
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO workouts (exercise_name, sets, reps, weight, notes, date_logged) 
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (exercise_name, sets, reps, weight, notes, date))

    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Workout saved successfully!'}), 200

@app.route('/get_weight_history', methods=['GET'])
def get_weight_history():
    # Placeholder for weight tracking - you can implement this later
    return jsonify({'dates': [], 'weights': []}), 200

@app.route('/get_volume_history', methods=['GET'])
def get_volume_history():
    # Placeholder for volume tracking - you can implement this later
    return jsonify({'weeks': [], 'volumes': []}), 200

@app.route('/get_exercise_list', methods=['GET'])
def get_exercise_list():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT DISTINCT exercise_name FROM weekly_plan ORDER BY exercise_name')
    exercises = [row[0] for row in cursor.fetchall()]

    conn.close()
    return jsonify({'exercises': exercises}), 200

@app.route('/get_exercise_performance/<exercise_name>', methods=['GET'])
def get_exercise_performance(exercise_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT date_logged, weight, sets, reps
        FROM workouts 
        WHERE LOWER(exercise_name) = LOWER(?)
        ORDER BY date_logged
    ''', (exercise_name,))

    data = cursor.fetchall()
    conn.close()

    if not data:
        return jsonify({'dates': [], 'max_weights': [], 'has_real_data': False}), 200

    dates = [row[0] for row in data]
    weights = []

    for row in data:
        try:
            weight_str = str(row[1]).replace('lbs', '').replace('kg', '').strip()
            if weight_str.lower() != 'bodyweight':
                weights.append(float(weight_str))
            else:
                weights.append(0)
        except:
            weights.append(0)

    return jsonify({
        'dates': dates,
        'max_weights': weights,
        'best_weight': max(weights) if weights else 0,
        'best_date': dates[weights.index(max(weights))] if weights else '',
        'total_sessions': len(dates),
        'progress': ((weights[-1] - weights[0]) / weights[0] * 100) if len(weights) > 1 and weights[0] > 0 else 0,
        'has_real_data': True
    }), 200

@app.route('/log_weight', methods=['POST'])
def log_weight():
    # Placeholder for weight logging - you can implement this later
    return jsonify({'success': True}), 200

@app.route('/update_profile', methods=['POST'])
def update_profile():
    field_name = request.form.get('field_name')
    value = request.form.get('value')

    if not field_name or not value:
        return redirect(url_for('profile'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Map form field names to database columns
    field_map = {
        'current_weight': 'current_weight',
        'injuries_history': 'injuries_history',
        'current_limitations': 'current_limitations',
        'primary_goal': 'primary_goal',
        'fitness_level': 'fitness_level',
        'training_frequency': 'training_frequency'
    }

    if field_name in field_map:
        db_field = field_map[field_name]
        cursor.execute(f'UPDATE user_background SET {db_field} = ?, updated_date = ? WHERE user_id = 1', 
                      (value, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

    conn.close()
    return redirect(url_for('profile'))

# Flask app configuration to run properly on Replit
if __name__ == "__main__":
    init_db()