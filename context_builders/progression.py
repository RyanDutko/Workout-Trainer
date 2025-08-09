
import sqlite3

def build_progression_context():
    """Build context for progression queries - recent performance trends"""
    print("🔍 Building progression context")
    
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    context_info = "\n=== PROGRESSION CONTEXT ===\n"
    
    # Get recent workouts for trend analysis
    cursor.execute("""
        SELECT exercise_name, sets, reps, weight, date_logged, substitution_reason, notes
        FROM workouts
        WHERE date_logged >= date('now', '-14 days')
        ORDER BY exercise_name, date_logged DESC
    """)
    recent_logs = cursor.fetchall()

    if recent_logs:
        context_info += "Recent Performance (last 2 weeks):\n"
        for log in recent_logs[:15]:
            exercise, sets, reps, weight, date, sub_reason, notes = log
            context_info += f"• {exercise}: {sets}x{reps}@{weight} ({date})"
            if sub_reason:
                context_info += f" - Substituted: {sub_reason}"
            if notes:
                context_info += f" - {notes[:50]}{'...' if len(notes) > 50 else ''}"
            context_info += "\n"

    # Include current weekly plan targets
    cursor.execute('SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight FROM weekly_plan ORDER BY exercise_name')
    planned_exercises = cursor.fetchall()
    if planned_exercises:
        context_info += "\nCurrent Weekly Plan Targets:\n"
        for day, exercise, sets, reps, weight in planned_exercises:
            context_info += f"• {exercise}: {sets}x{reps}@{weight} ({day})\n"

    print(f"✅ Built progression context with {len(recent_logs)} recent workouts")
    conn.close()
    return context_info
