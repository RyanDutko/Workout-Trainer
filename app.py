
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import datetime
import json
import sys
import os

# Prevent main.py from running its console loop when imported
sys.argv = ['app.py']  # Override sys.argv to prevent main.py console execution

from main import (
    call_grok_parse, get_grok_response, update_background_field
)

# Create Flask-specific database functions to avoid threading issues
def get_db_connection():
    """Create a new database connection for each request"""
    conn = sqlite3.connect('workout_logs.db')
    return conn

def get_user_profile():
    """Get user profile with Flask-safe database connection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT goal, weekly_split, preferences FROM users WHERE id = 1")
    result = cursor.fetchone()
    conn.close()
    return result if result else ("", "", "")

def get_weekly_plan(day=None):
    """Get weekly plan with Flask-safe database connection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    if day:
        cursor.execute('''
            SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
            FROM weekly_plan 
            WHERE day_of_week = ?
            ORDER BY exercise_order
        ''', (day.lower(),))
    else:
        cursor.execute('''
            SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
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
    result = cursor.fetchall()
    conn.close()
    return result

def get_user_background():
    """Get user background with Flask-safe database connection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT age, gender, height, current_weight, fitness_level, years_training, 
               primary_goal, secondary_goals, injuries_history, current_limitations,
               past_weight_loss, past_weight_gain, medical_conditions, training_frequency,
               available_equipment, time_per_session, preferred_training_style,
               motivation_factors, biggest_challenges, past_program_experience,
               nutrition_approach, sleep_quality, stress_level, additional_notes,
               chat_response_style, chat_progression_detail
        FROM user_background WHERE user_id = 1
    """)
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            'age': result[0], 'gender': result[1], 'height': result[2], 
            'current_weight': result[3], 'fitness_level': result[4], 
            'years_training': result[5], 'primary_goal': result[6],
            'secondary_goals': result[7], 'injuries_history': result[8],
            'current_limitations': result[9], 'past_weight_loss': result[10],
            'past_weight_gain': result[11], 'medical_conditions': result[12],
            'training_frequency': result[13], 'available_equipment': result[14],
            'time_per_session': result[15], 'preferred_training_style': result[16],
            'motivation_factors': result[17], 'biggest_challenges': result[18],
            'past_program_experience': result[19], 'nutrition_approach': result[20],
            'sleep_quality': result[21], 'stress_level': result[22],
            'additional_notes': result[23], 'chat_response_style': result[24],
            'chat_progression_detail': result[25]
        }
    return None

def get_grok_preferences():
    """Get Grok preferences with Flask-safe database connection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT grok_tone, grok_detail_level, grok_format, preferred_units, communication_style, technical_level 
        FROM users WHERE id = 1
    """)
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            'tone': result[0],
            'detail_level': result[1], 
            'format': result[2],
            'units': result[3],
            'communication_style': result[4],
            'technical_level': result[5]
        }
    return {
        'tone': 'motivational',
        'detail_level': 'concise', 
        'format': 'bullet_points',
        'units': 'lbs',
        'communication_style': 'encouraging',
        'technical_level': 'beginner'
    }

def is_onboarding_complete():
    """Check if onboarding is complete with Flask-safe database connection"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT onboarding_completed FROM user_background WHERE user_id = 1")
    result = cursor.fetchone()
    conn.close()
    return result and result[0]

def insert_log(entry, date_logged):
    """Insert workout log with Flask-safe database connection"""
    if not entry:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO workouts (exercise_name, sets, reps, weight, date_logged, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        entry.get("exercise_name", "Unknown"),
        entry.get("sets", 1),
        entry.get("reps", "Unknown"),
        entry.get("weight", "0"),
        date_logged.isoformat(),
        entry.get("notes", "")
    ))
    
    conn.commit()
    conn.close()

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

@app.route('/')
def dashboard():
    """Main dashboard showing today's plan and recent workouts"""
    # Get today's plan
    today = datetime.date.today().strftime('%A').lower()
    today_plan = get_weekly_plan(today)
    
    # Get recent workouts
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT exercise_name, sets, reps, weight, date_logged 
        FROM workouts 
        ORDER BY date_logged DESC 
        LIMIT 10
    """)
    recent_workouts = cursor.fetchall()
    conn.close()
    
    # Check if onboarding is needed
    needs_onboarding = not is_onboarding_complete()
    
    return render_template('dashboard.html', 
                         today=today.title(),
                         today_plan=today_plan,
                         recent_workouts=recent_workouts,
                         needs_onboarding=needs_onboarding)

@app.route('/log_workout', methods=['GET', 'POST'])
def log_workout():
    """Log a new workout"""
    if request.method == 'POST':
        workout_text = request.form['workout_text']
        date_str = request.form.get('date', datetime.date.today().isoformat())
        date_logged = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        
        entry = call_grok_parse(workout_text, date_logged)
        if entry:
            insert_log(entry, date_logged)
            flash(f"✅ Logged: {entry['exercise_name']} - {entry['sets']}x{entry['reps']}@{entry['weight']}", 'success')
        else:
            flash("⚠️ Couldn't parse workout. Try format like '3x10@200lbs bench press'", 'error')
        
        return redirect(url_for('dashboard'))
    
    # Pass current date and today's plan to template
    today_date = datetime.date.today().isoformat()
    today_name = datetime.date.today().strftime('%A').lower()
    today_plan = get_weekly_plan(today_name)
    
    # Debug: print what we're getting
    print(f"DEBUG: Today is {today_name}, plan: {today_plan}")
    
    return render_template('log_workout.html', today=today_date, today_plan=today_plan, today_name=today_name.title())

@app.route('/weekly_plan')
def weekly_plan():
    """View and manage weekly workout plan"""
    plan = get_weekly_plan()
    
    # Organize by day
    plan_by_day = {}
    for row in plan:
        day, exercise, sets, reps, weight, order, notes = row
        if day not in plan_by_day:
            plan_by_day[day] = []
        plan_by_day[day].append({
            'exercise': exercise,
            'sets': sets,
            'reps': reps,
            'weight': weight,
            'order': order,
            'notes': notes
        })
    
    # Debug: print what we found
    print(f"DEBUG: Weekly plan loaded, found {len(plan)} total exercises")
    for day, exercises in plan_by_day.items():
        print(f"DEBUG: {day}: {len(exercises)} exercises - {[ex['exercise'] for ex in exercises]}")
    
    return render_template('weekly_plan.html', plan_by_day=plan_by_day)

@app.route('/add_to_plan', methods=['POST'])
def add_to_plan():
    """Add exercise to weekly plan"""
    day = request.form['day']
    exercise = request.form['exercise']
    sets = int(request.form['sets'])
    reps = request.form['reps']
    weight = request.form['weight']
    
    # Add directly to database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current exercise count for this day to set order
    cursor.execute('SELECT COUNT(*) FROM weekly_plan WHERE day_of_week = ?', (day.lower(),))
    order = cursor.fetchone()[0] + 1
    
    cursor.execute('''
        INSERT OR REPLACE INTO weekly_plan 
        (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, created_date, updated_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (day.lower(), exercise.lower(), sets, reps, weight, order, "", 
          datetime.date.today().isoformat(), datetime.date.today().isoformat()))
    
    conn.commit()
    conn.close()
    
    flash(f"✅ Added to {day}: {exercise} {sets}x{reps}@{weight}", 'success')
    return redirect(url_for('weekly_plan'))

@app.route('/progression')
def progression():
    """Get AI progression suggestions"""
    return render_template('progression.html')

@app.route('/get_progression', methods=['POST'])
def get_progression():
    """API endpoint for detailed progression analysis"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get weekly plan organized by day
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
    
    # Get recent performance data
    cursor.execute('''
        SELECT exercise_name, sets, reps, weight, date_logged, notes
        FROM workouts 
        WHERE date_logged >= date('now', '-30 days')
        ORDER BY date_logged DESC
    ''')
    recent_workouts = cursor.fetchall()
    
    conn.close()

    if not weekly_plan:
        return jsonify({'error': 'No weekly plan found. Set up your plan first!'})

    # Build comprehensive context for analysis
    plan_by_day = {}
    for day, exercise, sets, reps, weight, order in weekly_plan:
        if day not in plan_by_day:
            plan_by_day[day] = []
        plan_by_day[day].append(f"{exercise}: {sets}x{reps}@{weight}")
    
    plan_text = ""
    for day, exercises in plan_by_day.items():
        plan_text += f"\n{day.title()}:\n"
        for exercise in exercises:
            plan_text += f"  • {exercise}\n"
    
    # Build recent performance summary
    performance_text = "\nRecent Performance (last 30 days):\n"
    exercise_performance = {}
    for exercise, sets, reps, weight, date, notes in recent_workouts:
        if exercise not in exercise_performance:
            exercise_performance[exercise] = []
        exercise_performance[exercise].append(f"{sets}x{reps}@{weight} ({date}) {notes}")
    
    for exercise, performances in exercise_performance.items():
        performance_text += f"\n{exercise}:\n"
        for perf in performances[:3]:  # Show last 3 sessions
            performance_text += f"  - {perf}\n"

    progression_prompt = f"""You are reviewing a user's workout program during their rest day. Take a thoughtful, analytical approach as if you're a coach reviewing their progress.

CURRENT WEEKLY PLAN:{plan_text}

{performance_text}

Provide a comprehensive progression analysis that includes:

1. **PROGRAM OVERVIEW**: Brief summary of what's working well in their current split
2. **OBSERVATIONS**: Patterns you notice from recent performance data
3. **READY FOR PROGRESSION**: Exercises where they should increase weight/reps next week
4. **MONITOR CLOSELY**: Exercises to keep same weight but watch for readiness signs
5. **TECHNIQUE FOCUS**: Exercises where form/consistency should be priority
6. **UPCOMING CHANGES**: Longer-term adjustments to consider

Be conversational but analytical. Show that you've reviewed their data thoroughly. Include specific numbers and reasoning. Format with clear sections using markdown headers."""

    response = get_grok_response(progression_prompt, include_context=True)
    return jsonify({'suggestions': response})

@app.route('/profile')
def profile():
    """View and edit user profile"""
    background = get_user_background()
    preferences = get_grok_preferences()
    goal, weekly_split, prefs = get_user_profile()
    
    return render_template('profile.html', 
                         background=background,
                         preferences=preferences,
                         goal=goal,
                         weekly_split=weekly_split)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    """Update user profile information"""
    field_name = request.form['field_name']
    value = request.form['value']
    
    result = update_background_field(field_name, value)
    flash(result, 'success')
    
    return redirect(url_for('profile'))

@app.route('/history')
def history():
    """View workout history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT exercise_name, sets, reps, weight, date_logged, notes, id 
        FROM workouts 
        ORDER BY date_logged DESC 
        LIMIT 100
    """)
    workouts = cursor.fetchall()
    conn.close()
    
    return render_template('history.html', workouts=workouts)

@app.route('/delete_workout', methods=['POST'])
def delete_workout():
    """Delete a specific workout"""
    try:
        data = request.get_json()
        workout_id = data.get('workout_id')
        
        if not workout_id:
            return jsonify({'success': False, 'error': 'No workout ID provided'})
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Workout not found'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_plan/<date>')
def get_plan_for_date(date):
    """API endpoint to get plan for specific date"""
    try:
        selected_date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
        day_name = selected_date.strftime('%A').lower()
        plan = get_weekly_plan(day_name)
        
        return jsonify({
            'day_name': day_name.title(),
            'plan': plan
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/log_multi_workout', methods=['POST'])
def log_multi_workout():
    """Log multiple exercises in one session"""
    try:
        data = request.get_json()
        exercises = data.get('exercises', [])
        date_str = data.get('date', datetime.date.today().isoformat())
        date_logged = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        
        if not exercises:
            return jsonify({'success': False, 'error': 'No exercises provided'})
        
        # Log each exercise
        for exercise in exercises:
            insert_log(exercise, date_logged)
        
        return jsonify({'success': True, 'message': f'Logged {len(exercises)} exercises'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/reorder_exercise', methods=['POST'])
def reorder_exercise():
    """Reorder exercises in weekly plan"""
    try:
        data = request.get_json()
        day = data.get('day')
        exercise = data.get('exercise')
        direction = data.get('direction')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current exercise order
        cursor.execute('SELECT exercise_order FROM weekly_plan WHERE day_of_week = ? AND exercise_name = ?', 
                      (day.lower(), exercise.lower()))
        result = cursor.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Exercise not found'})
        
        current_order = result[0]
        
        if direction == 'up':
            new_order = current_order - 1
            # Find exercise to swap with
            cursor.execute('SELECT exercise_name FROM weekly_plan WHERE day_of_week = ? AND exercise_order = ?',
                          (day.lower(), new_order))
            swap_exercise = cursor.fetchone()
            
            if swap_exercise:
                # Swap orders
                cursor.execute('UPDATE weekly_plan SET exercise_order = ? WHERE day_of_week = ? AND exercise_name = ?',
                              (new_order, day.lower(), exercise.lower()))
                cursor.execute('UPDATE weekly_plan SET exercise_order = ? WHERE day_of_week = ? AND exercise_name = ?',
                              (current_order, day.lower(), swap_exercise[0]))
        
        elif direction == 'down':
            new_order = current_order + 1
            # Find exercise to swap with
            cursor.execute('SELECT exercise_name FROM weekly_plan WHERE day_of_week = ? AND exercise_order = ?',
                          (day.lower(), new_order))
            swap_exercise = cursor.fetchone()
            
            if swap_exercise:
                # Swap orders
                cursor.execute('UPDATE weekly_plan SET exercise_order = ? WHERE day_of_week = ? AND exercise_name = ?',
                              (new_order, day.lower(), exercise.lower()))
                cursor.execute('UPDATE weekly_plan SET exercise_order = ? WHERE day_of_week = ? AND exercise_name = ?',
                              (current_order, day.lower(), swap_exercise[0]))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    """Chat with AI trainer"""
    if request.method == 'POST':
        user_message = request.form['message']
        
        # Build enhanced context for chat
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get user's chat preferences
        cursor.execute("""
            SELECT chat_response_style, chat_progression_detail 
            FROM user_background WHERE user_id = 1
        """)
        chat_prefs = cursor.fetchone()
        if chat_prefs:
            response_style, progression_detail = chat_prefs
        else:
            response_style = "exercise_by_exercise_breakdown"
            progression_detail = "include_specific_progression_notes_per_exercise"
        
        # Enhanced prompt for better responses
        chat_prompt = f"""You are a personal trainer having a conversation with your client. 

IMPORTANT RESPONSE GUIDELINES:
- Response Style: {response_style}
- Progression Detail: {progression_detail}
- When showing workout plans, break down each exercise individually with progression notes
- Be conversational but detailed
- If asked about specific days, show exercise-by-exercise breakdown with progression suggestions for each
- Always consider their recent performance when giving progression advice

User Question: {user_message}

RESPONSE FORMAT for workout plan questions:
If they ask about a specific day's plan, format like this:

**Monday Workout Plan:**

**Exercise 1: [Exercise Name]**
- Current: [sets]x[reps]@[weight] 
- Progression Note: [specific advice for this exercise based on recent performance]

**Exercise 2: [Exercise Name]**
- Current: [sets]x[reps]@[weight]
- Progression Note: [specific advice for this exercise based on recent performance]

Continue this format for all exercises in that day."""

        conn.close()
        
        response = get_grok_response(chat_prompt, include_context=True)
        return jsonify({'response': response})
    
    return render_template('chat.html')

if __name__ == '__main__':
    print("🌐 Starting Flask web server...")
    print("🔗 Access your web app at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
