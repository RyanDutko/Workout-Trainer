from flask import Flask, render_template, request, jsonify, Response
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
        complex_structure TEXT
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
        actions_taken TEXT,
        workout_context TEXT,
        exercise_mentioned TEXT,
        form_cues_given TEXT,
        performance_notes TEXT,
        plan_modifications TEXT,
        timestamp TEXT DEFAULT (datetime('now', 'localtime')),
        session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
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

    # Add missing columns if they don't exist (for existing databases)
    columns_to_add = [
        ('target_sets', 'INTEGER DEFAULT 3'),
        ('target_reps', 'TEXT DEFAULT "8-10"'),
        ('target_weight', 'TEXT DEFAULT "0lbs"'),
        ('exercise_order', 'INTEGER DEFAULT 1'),
        ('exercise_type', 'TEXT DEFAULT "working_set"'),
        ('progression_rate', 'TEXT DEFAULT "normal"'),
        ('created_by', 'TEXT DEFAULT "user"')
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

def analyze_query_intent(prompt):
    """Analyze the query to determine what type of context to include"""
    prompt_lower = prompt.lower()

    # Full plan review (comprehensive analysis)
    if 'FULL_PLAN_REVIEW_REQUEST:' in prompt:
        return 'full_plan_review'

    # Progression-related queries
    if any(word in prompt_lower for word in ['progress', 'increase', 'heavier', 'next week', 'bump up', 'advance']):
        return 'progression'

    # Exercise-specific queries
    exercise_names = ['bench', 'squat', 'deadlift', 'press', 'curl', 'row', 'pull']
    if any(exercise in prompt_lower for exercise in exercise_names):
        return 'exercise_specific'

    # General fitness chat
    if any(word in prompt_lower for word in ['hello', 'hi', 'how are', 'what can', 'help']):
        return 'general'

    # Historical queries
    if any(word in prompt_lower for word in ['did', 'last', 'history', 'previous', 'ago']):
        return 'historical'

    return 'general'

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

RESPONSE LENGTH GUIDELINES:
- Greetings ("hello", "hi"): Very brief (1-2 sentences)
- General questions ("what can you do"): Moderate length with bullet points
- Historical data ("what did I do Friday"): Brief summary format
- Progression tips: Use this specific format:
  • Exercise Name: specific actionable change (e.g., "bump up to 40 lbs", "go for 25 reps")
  • Exercise Name: specific actionable change
  Then end with: "Ask for my reasoning on any of these progressions if you'd like more detail."

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

    # Get today's plan - select specific columns to match template unpacking
    cursor.execute('SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, COALESCE(notes, "") FROM weekly_plan WHERE day_of_week = ? ORDER BY exercise_order', (today_lowercase,))
    today_plan = cursor.fetchall()

    # Get recent workouts
    cursor.execute('SELECT exercise_name, sets, reps, weight, date_logged FROM workouts ORDER BY date_logged DESC LIMIT 10')
    recent_workouts = cursor.fetchall()

    # Calculate stats
    from collections import namedtuple
    Stats = namedtuple('Stats', ['week_volume', 'month_volume', 'week_workouts', 'latest_weight', 'weight_date'])

    # Week volume
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    cursor.execute('SELECT SUM(CAST(weight AS REAL) * sets * CAST(reps AS REAL)) FROM workouts WHERE date_logged >= ?', (week_ago,))
    week_volume = cursor.fetchone()[0] or 0

    # Month volume
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    cursor.execute('SELECT SUM(CAST(weight AS REAL) * sets * CAST(reps AS REAL)) FROM workouts WHERE date_logged >= ?', (month_ago,))
    month_volume = cursor.fetchone()[0] or 0

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
                         today_plan=today_plan, 
                         recent_workouts=recent_workouts,
                         stats=stats,
                         needs_onboarding=needs_onboarding)

@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/chat_stream', methods=['POST'])
def chat_stream():
    # Get the message outside the generator to avoid context issues
    user_message = request.form.get('message', '')
    conversation_history = request.form.get('conversation_history', '')
    print(f"Chat request received: {user_message}")  # Debug log

    def generate():
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
            if conversation_history and len(conversation_history) > 50:
                # This is a follow-up question - include recent conversation context
                context_prompt = f"PREVIOUS CONVERSATION:\n{conversation_history[-1000:]}\n\nUSER'S FOLLOW-UP: {user_message}"
                response = get_grok_response_with_context(context_prompt, user_background, recent_workouts)
            else:
                # First message or no significant history
                response = get_grok_response_with_context(user_message, user_background, recent_workouts)
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

                # Detect intent and extract context
                detected_intent = analyze_query_intent(user_message)

                # Extract exercise mentions
                exercise_keywords = ['bench', 'squat', 'deadlift', 'press', 'curl', 'row', 'pull', 'leg', 'chest', 'back', 'shoulder']
                exercise_mentioned = None
                for keyword in exercise_keywords:
                    if keyword in user_message.lower():
                        exercise_mentioned = keyword
                        break

                # Store conversation
                cursor.execute('''
                    INSERT INTO conversations 
                    (user_message, ai_response, detected_intent, exercise_mentioned, session_id, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_message, response, detected_intent, exercise_mentioned, session_id, 
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

                conn.commit()
                conn.close()
                print(f"💾 Stored conversation with intent: {detected_intent}")

            except Exception as e:
                print(f"⚠️ Failed to store conversation: {str(e)}")

        except Exception as e:
            print(f"Chat stream error: {str(e)}")  # Debug log
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/plain')

@app.route('/log_workout')
def log_workout():
    today = datetime.now().strftime('%Y-%m-%d')
    today_name = datetime.now().strftime('%A')
    return render_template('log_workout.html', today=today, today_name=today_name)

@app.route('/history')
def history():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    cursor.execute('SELECT exercise_name, sets, reps, weight, date_logged, notes, id FROM workouts ORDER BY date_logged DESC')
    workouts = cursor.fetchall()
    conn.close()
    return render_template('history.html', workouts=workouts)

@app.route('/weekly_plan')
def weekly_plan():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check what columns actually exist
    cursor.execute("PRAGMA table_info(weekly_plan)")
    columns = [col[1] for col in cursor.fetchall()]

    # Use the correct column names based on what exists
    if 'target_sets' in columns:
        cursor.execute('SELECT id, day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes FROM weekly_plan ORDER BY day_of_week, exercise_order')
    else:
        cursor.execute('SELECT id, day_of_week, exercise_name, sets, reps, weight, order_index, COALESCE(notes, "") FROM weekly_plan ORDER BY day_of_week, order_index')

    plan_data = cursor.fetchall()
    conn.close()

    # Organize plan by day
    plan_by_day = {}
    for row in plan_data:
        id, day, exercise, sets, reps, weight, order, notes = row
        if day not in plan_by_day:
            plan_by_day[day] = []
        plan_by_day[day].append({
            'id': id,
            'exercise': exercise,
            'sets': sets,
            'reps': reps,
            'weight': weight,
            'order': order,
            'notes': notes or ""
        })

    return render_template('weekly_plan.html', plan_by_day=plan_by_day)

@app.route('/profile')
def profile():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()

    # Get user background
    cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY created_date DESC LIMIT 1')
    bg_result = cursor.fetchone()
    background = None

    if bg_result:
        columns = [description[0] for description in cursor.description]
        background = dict(zip(columns, bg_result))

    # Get user preferences
    cursor.execute('SELECT grok_tone, grok_detail_level, grok_format, preferred_units, communication_style, technical_level FROM users WHERE id = 1')
    pref_result = cursor.fetchone()

    preferences = {
        'tone': pref_result[0] if pref_result else 'motivational',
        'detail_level': pref_result[1] if pref_result else 'concise',
        'format': pref_result[2] if pref_result else 'bullet_points',
        'units': pref_result[3] if pref_result else 'lbs',
        'communication_style': pref_result[4] if pref_result else 'encouraging',
        'technical_level': pref_result[5] if pref_result else 'beginner'
    }

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
        cursor.execute('''
            SELECT plan_philosophy, training_style, weekly_structure, progression_strategy,
                   special_considerations, created_by_ai, creation_reasoning, created_date, updated_date
            FROM plan_context 
            WHERE user_id = 1 
            ORDER BY created_date DESC 
            LIMIT 1
        ''')

        plan_result = cursor.fetchone()
        plan_context = None

        if plan_result:
            plan_context = {
                'plan_philosophy': plan_result[0],
                'training_style': plan_result[1],
                'weekly_structure': plan_result[2],
                'progression_strategy': plan_result[3],
                'special_considerations': plan_result[4],
                'created_by_ai': bool(plan_result[5]),
                'creation_reasoning': plan_result[6],
                'created_date': plan_result[7],
                'updated_date': plan_result[8]
            }

        # Get exercise metadata
        cursor.execute('''
            SELECT exercise_name, exercise_type, primary_purpose, progression_logic, ai_notes, created_date
            FROM exercise_metadata 
            WHERE user_id = 1
            ORDER BY exercise_name
        ''')

        exercise_results = cursor.fetchall()
        exercise_metadata = []

        for row in exercise_results:
            exercise_metadata.append({
                'exercise_name': row[0],
                'exercise_type': row[1],
                'primary_purpose': row[2],
                'progression_logic': row[3],
                'ai_notes': row[4],
                'created_date': row[5]
            })

        conn.close()

        return jsonify({
            'plan_context': plan_context,
            'exercise_metadata': exercise_metadata
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
                    WHEN 'tuesday' THEN 2                     WHEN 'wednesday' THEN 3
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
                            'sets': instance['sets'],
                            'reps': instance['reps'],
                            'weight': instance['weight'],
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
                                purpose = "Midsection hypertrophy for loose skin tightening"
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
                            purpose = "Midsection hypertrophy for loose skin tightening"
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
                    purpose = "Midsection hypertrophy for loose skin tightening"
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

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)