
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
        sets INTEGER,
        reps TEXT,
        weight TEXT,
        order_index INTEGER DEFAULT 1,
        notes TEXT
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
    
    # Add order_index column if it doesn't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE weekly_plan ADD COLUMN order_index INTEGER DEFAULT 1')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    cursor.execute('INSERT OR IGNORE INTO users (id, goal, weekly_split, preferences) VALUES (1, "", "", "")')
    conn.commit()
    conn.close()

def get_grok_response_with_context(prompt, user_background=None, recent_workouts=None):
    """Enhanced Grok response with user context and workout history"""
    try:
        client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
        
        # Build context-aware prompt
        context_info = ""
        if user_background:
            context_info += f"User Profile: {user_background['primary_goal']}"
            if user_background['secondary_goals'] and user_background['secondary_goals'] != "None":
                context_info += f", {user_background['secondary_goals']}"
            if user_background['injuries_history'] and user_background['injuries_history'] != "None":
                context_info += f"\n- Injury History: {user_background['injuries_history']}"
            if user_background['current_limitations'] and user_background['current_limitations'] != "None":
                context_info += f"\n- Current Limitations: {user_background['current_limitations']}"
            context_info += f"\n- Training Frequency: {user_background['training_frequency']}"
            context_info += f"\n- Equipment: {user_background['available_equipment']}"
        
        if recent_workouts:
            context_info += f"\n\nRecent Workouts:\n{recent_workouts}"
        
        chat_prompt = f"{context_info}\n\nUser Question: {prompt}" if context_info else prompt
        
        # Detect query type for appropriate token allocation
        is_progression_query = any(word in prompt.lower() for word in ['progression', 'progress', 'next', 'increase', 'improve', 'advance'])
        is_history_query = any(word in prompt.lower() for word in ['show', 'what did', 'last', 'history', 'previous', 'when'])
        
        # Increase token limits for testing - we'll optimize later
        max_tokens = 1200 if (is_progression_query or is_history_query) else 600
        
        response = client.chat.completions.create(
            model="grok-4-0709",
            messages=[
                {"role": "system", "content": "You are a professional fitness assistant. Provide helpful, detailed responses about workouts, training, and fitness. Use the user's background information to personalize your advice. Do not introduce yourself with a name."},
                {"role": "user", "content": chat_prompt}
            ],
            temperature=0.3,
            max_tokens=max_tokens,
            timeout=30
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"⚠️ API error: {str(e)}")
        return f"Sorry, I'm having trouble connecting right now. Please try again in a moment."

@app.route('/')
def dashboard():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    # Get today's day of week
    today = datetime.now().strftime('%A')
    
    # Get today's plan
    cursor.execute('SELECT * FROM weekly_plan WHERE day_of_week = ? ORDER BY id', (today,))
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
    def generate():
        try:
            data = request.json
            user_message = data.get('message', '')
            
            # Get user background for context
            conn = sqlite3.connect('workout_logs.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM user_background WHERE user_id = 1 ORDER BY created_date DESC LIMIT 1')
            user_bg = cursor.fetchone()
            user_background = None
            
            if user_bg:
                columns = [description[0] for description in cursor.description]
                user_background = dict(zip(columns, user_bg))
            
            # Get recent workouts for context
            cursor.execute('SELECT exercise_name, sets, reps, weight, date_logged FROM workouts ORDER BY date_logged DESC LIMIT 10')
            recent_logs = cursor.fetchall()
            recent_workouts = ""
            if recent_logs:
                recent_workouts = "Recent exercises:\n"
                for log in recent_logs[:5]:  # Limit to 5 most recent
                    recent_workouts += f"- {log[0]}: {log[1]}x{log[2]} @ {log[3]} ({log[4]})\n"
            
            conn.close()
            
            # Get AI response with full context
            response = get_grok_response_with_context(user_message, user_background, recent_workouts)
            
            # Stream the response
            for char in response:
                yield f"data: {json.dumps({'content': char})}\n\n"
                time.sleep(0.01)  # Small delay for streaming effect
            
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/plain')

@app.route('/log_workout')
def log_workout():
    return render_template('log_workout.html')

@app.route('/history')
def history():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM workouts ORDER BY date_logged DESC')
    workouts = cursor.fetchall()
    conn.close()
    return render_template('history.html', workouts=workouts)

@app.route('/weekly_plan')
def weekly_plan():
    return render_template('weekly_plan.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/progression')
def progression():
    return render_template('progression.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/add_to_plan', methods=['POST'])
def add_to_plan():
    # Handle adding exercises to weekly plan
    return jsonify({'status': 'success'})

@app.route('/save_workout', methods=['POST'])
def save_workout():
    # Handle saving workouts
    return jsonify({'status': 'success'})

@app.route('/get_plan/<day>')
def get_plan(day):
    # Get plan for specific day
    return jsonify({'exercises': []})

if __name__ == '__main__':
    init_db()
    print("🌐 Starting Flask web server...")
    print("🔗 Access your web app at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
