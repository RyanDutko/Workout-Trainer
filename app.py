from flask import Flask, render_template, request, jsonify, Response
import sqlite3
import json
import os
from openai import OpenAI
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import time

app = Flask(__name__)

# Database initialization
def init_db():
    conn = sqlite3.connect('workout_logs.db')
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
        date_logged TEXT DEFAULT (datetime('now', 'localtime'))
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
        created_by TEXT DEFAULT 'user'
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
    
    for column_name, column_def in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE weekly_plan ADD COLUMN {column_name} {column_def}')
        except sqlite3.OperationalError:
            pass  # Column already exists

    cursor.execute('INSERT OR IGNORE INTO users (id, goal, weekly_split, preferences) VALUES (1, "", "", "")')

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

def get_grok_response_with_context(prompt, user_background=None, recent_workouts=None):
    """Context-aware Grok response that responds naturally like Grok would"""
    try:
        client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")

        # Always build full context but let Grok decide how to use it
        context_info = ""

        # Add user background context
        if user_background:
            if user_background.get('primary_goal'):
                context_info += f"User's Primary Goal: {user_background['primary_goal']}\n"
            if user_background.get('fitness_level'):
                context_info += f"Fitness Level: {user_background['fitness_level']}\n"
            if user_background.get('training_frequency'):
                context_info += f"Training Frequency: {user_background['training_frequency']}\n"

        # Add weekly plan context
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()
        cursor.execute('SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight FROM weekly_plan ORDER BY day_of_week, exercise_order')
        planned_exercises = cursor.fetchall()

        if planned_exercises:
            context_info += "\nWeekly Plan:\n"
            current_day = ""
            for day, exercise, sets, reps, weight in planned_exercises:
                if day != current_day:
                    if current_day != "":
                        context_info += "\n"
                    context_info += f"{day.title()}: "
                    current_day = day
                else:
                    context_info += ", "
                context_info += f"{exercise} {sets}x{reps}@{weight}"
            context_info += "\n"

        # Get recent workout data
        cursor.execute("""
            SELECT exercise_name, sets, reps, weight, date_logged, notes
            FROM workouts 
            ORDER BY date_logged DESC 
            LIMIT 50
        """)
        recent_workout_logs = cursor.fetchall()
        if recent_workout_logs:
            context_info += "\nRecent Workouts (last 50 entries): " + "; ".join([f"{w[0]} {w[1]}x{w[2]}@{w[3]} ({w[4]})" for w in recent_workout_logs])

        conn.close()

        # Build final prompt with context
        full_prompt = context_info + "\n\n" + prompt

        response = client.chat.completions.create(
                model="grok-4-0709",
                messages=[
                    {"role": "system", "content": """You are Grok, an AI assistant with access to the user's workout history and fitness profile. 

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

STYLE: Be direct and cut unnecessary filler words. Get straight to the point while staying helpful. Avoid introductory phrases like "Great question!" or "Here's what I think" - just dive into the answer."""},
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
    conn = sqlite3.connect('workout_logs.db')
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

            # Get AI response with full context
            response = get_grok_response_with_context(user_message, user_background, recent_workouts)
            print(f"AI response received: {len(response)} characters")  # Debug log

            # Stream the response
            for char in response:
                yield f"data: {json.dumps({'content': char})}\n\n"
                time.sleep(0.01)  # Small delay for streaming effect

            yield f"data: {json.dumps({'done': True})}\n\n"

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
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()

    # Check what columns actually exist
    cursor.execute("PRAGMA table_info(weekly_plan)")
    columns = [col[1] for col in cursor.fetchall()]

    # Use the correct column names based on what exists
    if 'target_sets' in columns:
        cursor.execute('SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes FROM weekly_plan ORDER BY day_of_week, exercise_order')
    else:
        cursor.execute('SELECT day_of_week, exercise_name, sets, reps, weight, order_index, COALESCE(notes, "") FROM weekly_plan ORDER BY day_of_week, order_index')

    plan_data = cursor.fetchall()
    conn.close()

    # Organize plan by day
    plan_by_day = {}
    for row in plan_data:
        day, exercise, sets, reps, weight, order, notes = row
        if day not in plan_by_day:
            plan_by_day[day] = []
        plan_by_day[day].append({
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

@app.route('/save_plan_context', methods=['POST'])
def save_plan_context():
    """Save the reasoning and context behind the current workout plan"""
    try:
        data = request.json
        
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO plan_context
            (user_id, plan_philosophy, training_style, weekly_structure, 
             progression_strategy, special_considerations, created_by_ai, 
             creation_reasoning, created_date, updated_date)
            VALUES (1, ?, ?, ?, ?, ?, FALSE, ?, ?, ?)
        ''', (
            data.get('philosophy'),
            data.get('training_style'), 
            data.get('weekly_structure'),
            data.get('progression_strategy'),
            data.get('special_considerations'),
            data.get('reasoning'),
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%Y-%m-%d')
        ))

        # Also store exercise-specific context
        exercises = data.get('exercises', [])
        cursor.execute('DELETE FROM exercise_metadata WHERE user_id = 1')
        
        for exercise in exercises:
            cursor.execute('''
                INSERT INTO exercise_metadata
                (user_id, exercise_name, exercise_type, primary_purpose, 
                 progression_logic, ai_notes, created_date)
                VALUES (1, ?, ?, ?, ?, ?, ?)
            ''', (
                exercise['name'],
                exercise.get('type', 'working_set'),
                exercise.get('purpose', ''),
                exercise.get('progression_logic', 'normal'),
                exercise.get('notes', ''),
                datetime.now().strftime('%Y-%m-%d')
            ))

        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Plan context saved successfully!'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/weekly_plan')
def api_weekly_plan():
    """API endpoint to get weekly plan data for progression interface"""
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order
        FROM weekly_plan 
        ORDER BY day_of_week, exercise_order
    ''')
    
    plan_data = cursor.fetchall()
    conn.close()
    
    # Organize by day
    plan_by_day = {}
    for day, exercise, sets, reps, weight, order in plan_data:
        if day not in plan_by_day:
            plan_by_day[day] = []
        
        plan_by_day[day].append({
            'exercise_name': exercise,
            'sets': sets,
            'reps': reps,
            'weight': weight,
            'order': order
        })
    
    return jsonify(plan_by_day)

@app.route('/get_progression', methods=['POST'])
def get_progression():
    """Get AI progression suggestions for review and approval"""
    try:
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get current weekly plan
        cursor.execute('''
            SELECT DISTINCT exercise_name, target_sets, target_reps, target_weight
            FROM weekly_plan 
            ORDER BY exercise_name
        ''')
        planned_exercises = cursor.fetchall()

        if not planned_exercises:
            return jsonify({'error': 'No weekly plan found. Set up your plan first!'})

        # Get user background for context
        cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY id DESC LIMIT 1')
        user_bg = cursor.fetchone()
        user_background = None
        if user_bg:
            columns = [description[0] for description in cursor.description]
            user_background = dict(zip(columns, user_bg))

        # Format weekly plan for Grok
        plan_text = ""
        for exercise_name, target_sets, target_reps, target_weight in planned_exercises:
            plan_text += f"• {exercise_name}: {target_sets}x{target_reps}@{target_weight}\n"

        # Get plan context and exercise metadata
        cursor.execute('SELECT plan_philosophy, progression_strategy, creation_reasoning FROM plan_context WHERE user_id = 1 ORDER BY created_date DESC LIMIT 1')
        context_result = cursor.fetchone()
        plan_context = ""
        if context_result:
            philosophy, strategy, reasoning = context_result
            plan_context = f"\n\nPLAN CONTEXT:\nPhilosophy: {philosophy}\nProgression Strategy: {strategy}\nOriginal AI Reasoning: {reasoning[:200]}..."

        # Get exercise metadata
        cursor.execute('SELECT exercise_name, exercise_type, primary_purpose, progression_logic FROM exercise_metadata')
        metadata_results = cursor.fetchall()
        exercise_context = ""
        if metadata_results:
            exercise_context = "\n\nEXERCISE CONTEXT:\n"
            for name, ex_type, purpose, logic in metadata_results:
                exercise_context += f"• {name}: {ex_type} - {purpose} (progression: {logic})\n"

        # Create enhanced progression prompt
        progression_prompt = f"""Based on this weekly workout plan, provide specific progression suggestions:

{plan_text}{plan_context}{exercise_context}

IMPORTANT CONTEXT RULES:
- Warmup/activation exercises should rarely get weight increases
- Exercises marked as "slow" progression need conservative changes
- "Maintain" exercises should not progress in weight
- Consider the overall training philosophy when suggesting changes

Please provide progression suggestions in THIS EXACT FORMAT (this is crucial for parsing):
• Exercise Name: specific actionable change (e.g., "bump up to 40 lbs", "go for 25 reps")
• Exercise Name: stay at current weight - brief reason why (e.g., "warmup exercise", "focus on form first")

For each exercise, either suggest a progression OR suggest staying at current weight with a brief reason."""

        # Get Grok's response with full context
        response = get_grok_response_with_context(progression_prompt, user_background)
        
        conn.close()
        return jsonify({'suggestions': response})
        
    except Exception as e:
        print(f"Progression error: {str(e)}")
        return jsonify({'error': f'Error getting progression suggestions: {str(e)}'})

@app.route('/get_last_week_weight', methods=['POST'])
def get_last_week_weight():
    """Get the weight used for an exercise in the last week"""
    try:
        data = request.json
        exercise_name = data.get('exercise_name', '').lower()
        
        if not exercise_name:
            return jsonify({'error': 'Exercise name required'})
        
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()
        
        # Get workouts from last week (7-14 days ago to avoid current week)
        week_ago_start = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        week_ago_end = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT weight 
            FROM workouts 
            WHERE LOWER(exercise_name) = ? 
            AND date_logged BETWEEN ? AND ?
            ORDER BY date_logged DESC 
            LIMIT 1
        ''', (exercise_name, week_ago_start, week_ago_end))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return jsonify({'last_weight': result[0]})
        else:
            return jsonify({'last_weight': None})
            
    except Exception as e:
        print(f"Error getting last week weight: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/apply_progression', methods=['POST'])
def apply_progression():
    """Apply approved progression changes to weekly plan"""
    try:
        data = request.json
        changes = data.get('changes', [])
        
        if not changes:
            return jsonify({'success': False, 'error': 'No changes provided'})

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        applied_count = 0
        for change in changes:
            exercise_name = change.get('exercise_name', '').lower()
            new_sets = change.get('sets')
            new_reps = change.get('reps') 
            new_weight = change.get('weight')
            
            if exercise_name and (new_sets or new_reps or new_weight):
                # Update the weekly plan
                update_parts = []
                values = []
                
                if new_sets:
                    update_parts.append('target_sets = ?')
                    values.append(new_sets)
                if new_reps:
                    update_parts.append('target_reps = ?')
                    values.append(new_reps)
                if new_weight:
                    update_parts.append('target_weight = ?')
                    values.append(new_weight)
                
                values.append(exercise_name)
                
                cursor.execute(f'''
                    UPDATE weekly_plan 
                    SET {', '.join(update_parts)}
                    WHERE exercise_name = ?
                ''', values)
                
                if cursor.rowcount > 0:
                    applied_count += 1

        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Applied {applied_count} progression changes to your weekly plan!'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/add_to_plan', methods=['POST'])
def add_to_plan():
    try:
        data = request.form
        day = data.get('day')
        exercise = data.get('exercise')
        sets = data.get('sets')
        reps = data.get('reps')
        weight = data.get('weight')

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get next order index for this day
        cursor.execute('SELECT MAX(order_index) FROM weekly_plan WHERE day_of_week = ?', (day,))
        result = cursor.fetchone()
        order_index = (result[0] or 0) + 1

        cursor.execute('''
            INSERT INTO weekly_plan (day_of_week, exercise_name, sets, reps, weight, order_index)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (day, exercise, sets, reps, weight, order_index))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/save_workout', methods=['POST'])
def save_workout():
    try:
        data = request.json
        exercise_name = data.get('exercise_name')
        sets = data.get('sets')
        reps = data.get('reps')
        weight = data.get('weight')
        notes = data.get('notes', '')

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO workouts (exercise_name, sets, reps, weight, notes)
            VALUES (?, ?, ?, ?, ?)
        ''', (exercise_name, sets, reps, weight, notes))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/get_plan/<day>')
def get_plan(day):
    if not day or day == '':
        return jsonify({'exercises': [], 'day_name': 'Unknown'})

    # Convert date string to day name if it's a date
    try:
        # If it's a date string like "2025-01-27", convert to day name
        if '-' in day and len(day) == 10:
            date_obj = datetime.strptime(day, '%Y-%m-%d')
            day = date_obj.strftime('%A').lower()
        else:
            day = day.lower()
    except:
        day = day.lower()

    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()

    # Check what columns actually exist and use appropriate query
    cursor.execute("PRAGMA table_info(weekly_plan)")
    columns = [col[1] for col in cursor.fetchall()]

    # Always use the correct column names based on actual table structure
    cursor.execute('SELECT exercise_name, target_sets, target_reps, target_weight FROM weekly_plan WHERE day_of_week = ? ORDER BY exercise_order', (day,))

    exercises = cursor.fetchall()
    conn.close()

    exercise_list = []
    for exercise in exercises:
        exercise_list.append({
            'exercise_name': exercise[0],
            'sets': exercise[1],
            'reps': exercise[2],
            'weight': exercise[3]
        })

    return jsonify({'exercises': exercise_list, 'day_name': day.title()})

@app.route('/delete_exercise', methods=['POST'])
def delete_exercise():
    try:
        data = request.json
        day = data.get('day')
        exercise = data.get('exercise')

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM weekly_plan WHERE day_of_week = ? AND exercise_name = ?', (day, exercise))
        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/onboarding')
def onboarding():
    return render_template('onboarding.html')

@app.route('/generate_ai_plan', methods=['POST'])
def generate_ai_plan():
    """Generate a complete workout plan using AI based on user input"""
    try:
        data = request.json
        
        # Store user background first
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()
        
        # Insert user background
        cursor.execute('''
            INSERT OR REPLACE INTO user_background 
            (user_id, age, gender, height, current_weight, fitness_level, years_training,
             primary_goal, secondary_goals, injuries_history, current_limitations,
             training_frequency, available_equipment, time_per_session, preferred_training_style,
             biggest_challenges, onboarding_completed, created_date, updated_date)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?, ?)
        ''', (
            data.get('age'), data.get('gender'), data.get('height'), data.get('current_weight'),
            data.get('fitness_level'), data.get('years_training'), data.get('primary_goal'),
            data.get('secondary_goals'), data.get('injuries_history'), data.get('current_limitations'),
            data.get('training_frequency'), data.get('available_equipment'), data.get('time_per_session'),
            data.get('preferred_training_style'), data.get('biggest_challenges'),
            datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d')
        ))

        # Create AI prompt for plan generation
        plan_prompt = f"""Create a complete weekly workout plan based on this user profile:

Age: {data.get('age')}, Gender: {data.get('gender')}, Height: {data.get('height')}, Weight: {data.get('current_weight')}
Fitness Level: {data.get('fitness_level')} ({data.get('years_training')} years training)
Primary Goal: {data.get('primary_goal')}
Secondary Goals: {data.get('secondary_goals', 'None')}
Injuries/Limitations: {data.get('injuries_history', 'None')} / {data.get('current_limitations', 'None')}
Training Frequency: {data.get('training_frequency')}
Available Equipment: {data.get('available_equipment')}
Session Length: {data.get('time_per_session')}
Preferred Style: {data.get('preferred_training_style')}
Biggest Challenges: {data.get('biggest_challenges')}

Please respond with:
1. PLAN_PHILOSOPHY: A brief explanation of your training approach for this user
2. WEEKLY_STRUCTURE: How you've organized their week and why
3. PROGRESSION_STRATEGY: Your approach to progressive overload for them
4. WORKOUT_PLAN: The actual weekly plan in this EXACT format:

monday:
exercise_name|sets|reps|weight|type|progression_rate|purpose
example: bench press|4|8-10|185lbs|working_set|normal|primary chest builder

tuesday:
(continue for each day with exercises)

Use these exercise types:
- warmup: Light movement prep
- activation: Muscle activation/mobility
- working_set: Main strength/hypertrophy work
- accessory: Supporting/isolation work
- cooldown: Recovery/stretching

Use these progression rates:
- slow: Conservative progression (injuries/limitations)
- normal: Standard progression
- aggressive: Faster progression (experienced lifters)
- maintain: No progression needed (warmup/mobility work)

Be specific with weights based on their experience level."""

        # Get AI response
        ai_response = get_grok_response_with_context(plan_prompt)
        
        # Parse the AI response
        lines = ai_response.split('\n')
        plan_philosophy = ""
        weekly_structure = ""
        progression_strategy = ""
        workout_data = {}
        current_day = None
        
        for line in lines:
            if line.strip().startswith('PLAN_PHILOSOPHY:'):
                plan_philosophy = line.replace('PLAN_PHILOSOPHY:', '').strip()
            elif line.strip().startswith('WEEKLY_STRUCTURE:'):
                weekly_structure = line.replace('WEEKLY_STRUCTURE:', '').strip()
            elif line.strip().startswith('PROGRESSION_STRATEGY:'):
                progression_strategy = line.replace('PROGRESSION_STRATEGY:', '').strip()
            elif line.strip().lower().endswith(':') and line.strip().lower().replace(':', '') in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                current_day = line.strip().lower().replace(':', '')
                workout_data[current_day] = []
            elif current_day and '|' in line and not line.strip().startswith('exercise_name'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 6:
                    workout_data[current_day].append({
                        'exercise_name': parts[0],
                        'sets': int(parts[1]) if parts[1].isdigit() else 3,
                        'reps': parts[2],
                        'weight': parts[3],
                        'exercise_type': parts[4],
                        'progression_rate': parts[5],
                        'purpose': parts[6] if len(parts) > 6 else ""
                    })

        # Store plan context
        cursor.execute('''
            INSERT OR REPLACE INTO plan_context
            (user_id, plan_philosophy, training_style, weekly_structure, progression_strategy,
             created_by_ai, creation_reasoning, created_date, updated_date)
            VALUES (1, ?, ?, ?, ?, TRUE, ?, ?, ?)
        ''', (
            plan_philosophy, data.get('preferred_training_style'), weekly_structure, 
            progression_strategy, ai_response, datetime.now().strftime('%Y-%m-%d'), 
            datetime.now().strftime('%Y-%m-%d')
        ))

        # Clear existing plan and insert new one
        cursor.execute('DELETE FROM weekly_plan WHERE day_of_week IN ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")')
        cursor.execute('DELETE FROM exercise_metadata')

        # Insert new plan with metadata
        for day, exercises in workout_data.items():
            for i, exercise in enumerate(exercises, 1):
                cursor.execute('''
                    INSERT INTO weekly_plan
                    (day_of_week, exercise_name, target_sets, target_reps, target_weight,
                     exercise_order, exercise_type, progression_rate, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ai')
                ''', (
                    day, exercise['exercise_name'], exercise['sets'], exercise['reps'],
                    exercise['weight'], i, exercise['exercise_type'], exercise['progression_rate']
                ))

                # Store exercise metadata
                cursor.execute('''
                    INSERT INTO exercise_metadata
                    (user_id, exercise_name, exercise_type, primary_purpose, progression_logic, ai_notes, created_date)
                    VALUES (1, ?, ?, ?, ?, ?, ?)
                ''', (
                    exercise['exercise_name'], exercise['exercise_type'], exercise.get('purpose', ''),
                    exercise['progression_rate'], f"AI-generated for {data.get('primary_goal')}", 
                    datetime.now().strftime('%Y-%m-%d')
                ))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'AI-generated workout plan created successfully!',
            'plan_summary': {
                'philosophy': plan_philosophy,
                'structure': weekly_structure,
                'progression': progression_strategy
            }
        })

    except Exception as e:
        print(f"Error generating AI plan: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_profile', methods=['POST'])
def update_profile():
    try:
        field_name = request.form.get('field_name')
        value = request.form.get('value')

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Check if user background exists
        cursor.execute('SELECT COUNT(*) FROM user_background WHERE user_id = 1')
        if cursor.fetchone()[0] == 0:
            # Create initial record
            cursor.execute('INSERT INTO user_background (user_id) VALUES (1)')

        # Update the specified field
        valid_fields = ['current_weight', 'injuries_history', 'current_limitations', 'primary_goal', 'fitness_level', 'training_frequency']
        if field_name in valid_fields:
            cursor.execute(f'UPDATE user_background SET {field_name} = ?, updated_date = datetime("now") WHERE user_id = 1', (value,))
            conn.commit()

        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/reorder_exercise', methods=['POST'])
def reorder_exercise():
    try:
        data = request.json
        day = data.get('day')
        exercise = data.get('exercise')
        direction = data.get('direction')

        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get current exercise order
        cursor.execute('SELECT order_index FROM weekly_plan WHERE day_of_week = ? AND exercise_name = ?', (day, exercise))
        result = cursor.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Exercise not found'})

        current_order = result[0]

        if direction == 'up' and current_order > 1:
            new_order = current_order - 1
            # Swap with exercise above
            cursor.execute('UPDATE weekly_plan SET order_index = ? WHERE day_of_week = ? AND order_index = ?', (current_order, day, new_order))
            cursor.execute('UPDATE weekly_plan SET order_index = ? WHERE day_of_week = ? AND exercise_name = ?', (new_order, day, exercise))
        elif direction == 'down':
            cursor.execute('SELECT MAX(order_index) FROM weekly_plan WHERE day_of_week = ?', (day,))
            max_order = cursor.fetchone()[0]
            if current_order < max_order:
                new_order = current_order + 1
                # Swap with exercise below
                cursor.execute('UPDATE weekly_plan SET order_index = ? WHERE day_of_week = ? AND order_index = ?', (current_order, day, new_order))
                cursor.execute('UPDATE weekly_plan SET order_index = ? WHERE day_of_week = ? AND exercise_name = ?', (new_order, day, exercise))

        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    init_db()
    print("🌐 Starting Flask web server...")
    print("🔗 Access your web app at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)