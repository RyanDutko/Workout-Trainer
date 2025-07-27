
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import datetime
import json
import sys
import os

# Prevent main.py from running its console loop when imported
sys.argv = ['app.py']  # Override sys.argv to prevent main.py console execution

from main import (
    get_user_profile, get_weekly_plan, get_user_background, get_grok_preferences,
    manage_weekly_plan, manage_background, manage_preferences, call_grok_parse,
    insert_log, extract_date, get_grok_response, is_onboarding_complete,
    run_onboarding, update_background_field
)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

@app.route('/')
def dashboard():
    """Main dashboard showing today's plan and recent workouts"""
    # Get today's plan
    today = datetime.date.today().strftime('%A').lower()
    today_plan = get_weekly_plan(today)
    
    # Get recent workouts
    conn = sqlite3.connect('workout_logs.db')
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
    
    return render_template('log_workout.html')

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
    
    return render_template('weekly_plan.html', plan_by_day=plan_by_day)

@app.route('/add_to_plan', methods=['POST'])
def add_to_plan():
    """Add exercise to weekly plan"""
    day = request.form['day']
    exercise = request.form['exercise']
    sets = int(request.form['sets'])
    reps = request.form['reps']
    weight = request.form['weight']
    
    # Use existing function
    plan_input = f"set {day} {exercise} {sets}x{reps}@{weight}"
    result = manage_weekly_plan(plan_input)
    flash(result, 'success')
    
    return redirect(url_for('weekly_plan'))

@app.route('/progression')
def progression():
    """Get AI progression suggestions"""
    return render_template('progression.html')

@app.route('/get_progression', methods=['POST'])
def get_progression():
    """API endpoint for progression suggestions"""
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT exercise_name, target_sets, target_reps, target_weight
        FROM weekly_plan 
        ORDER BY exercise_name
    ''')
    planned_exercises = cursor.fetchall()
    conn.close()

    if not planned_exercises:
        return jsonify({'error': 'No weekly plan found. Set up your plan first!'})

    # Format weekly plan for Grok
    plan_text = ""
    for exercise_name, sets, reps, weight in planned_exercises:
        plan_text += f"• {exercise_name}: {sets}x{reps}@{weight}\n"

    progression_prompt = f"""Based on this weekly workout plan, provide specific progression suggestions:

{plan_text}

Please provide progression suggestions in this exact format:
• exercise name: specific suggestion

Keep suggestions practical and progressive (small weight increases, rep adjustments, etc.). Be concise and specific with numbers."""

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
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT exercise_name, sets, reps, weight, date_logged, notes 
        FROM workouts 
        ORDER BY date_logged DESC 
        LIMIT 50
    """)
    workouts = cursor.fetchall()
    conn.close()
    
    return render_template('history.html', workouts=workouts)

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    """Chat with AI trainer"""
    if request.method == 'POST':
        user_message = request.form['message']
        response = get_grok_response(f"Respond as a personal trainer to: {user_message}")
        return jsonify({'response': response})
    
    return render_template('chat.html')

if __name__ == '__main__':
    print("🌐 Starting Flask web server...")
    print("🔗 Access your web app at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
