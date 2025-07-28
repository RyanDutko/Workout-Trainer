
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
    """Full context-aware Grok response - restored working version"""
    try:
        client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
        
        # Build comprehensive context like the working version
        context_info = ""
        
        # Add user background context
        if user_background:
            if user_background.get('primary_goal'):
                context_info += f"User's Primary Goal: {user_background['primary_goal']}\n"
            if user_background.get('fitness_level'):
                context_info += f"Fitness Level: {user_background['fitness_level']}\n"
            if user_background.get('training_frequency'):
                context_info += f"Training Frequency: {user_background['training_frequency']}\n"
        
        # Add weekly plan context for progression queries
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

        # Get recent workout data for context
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
                {"role": "system", "content": "You are a helpful personal trainer AI with access to the user's workout history and profile."},
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
