
import sqlite3

def build_general_context(prompt, user_background=None):
    """Build minimal context for general chat"""
    print("🔍 Building general context")
    
    context_info = ""
    
    # Basic user info
    if user_background:
        if user_background.get('primary_goal'):
            context_info += f"User's Goal: {user_background['primary_goal']}\n"
        if user_background.get('fitness_level'):
            context_info += f"Fitness Level: {user_background['fitness_level']}\n"

    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    context_info += "\n=== BASIC INFO ===\n"
    cursor.execute('SELECT COUNT(*) FROM workouts WHERE date_logged >= date("now", "-7 days")')
    recent_count = cursor.fetchone()[0]
    context_info += f"Workouts this week: {recent_count}\n"

    # Include weekly plan if query mentions days or exercises
    if any(day in prompt.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']) or any(word in prompt.lower() for word in ['plan', 'schedule', 'workout', 'exercise']):
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
            context_info += "\n=== WEEKLY PLAN ===\n"
            current_day = ""
            for row in weekly_plan:
                day, exercise, sets, reps, weight, order = row
                if day != current_day:
                    if current_day:
                        context_info += "\n"
                    context_info += f"\n{day.upper()}:\n"
                    current_day = day
                context_info += f"  {order}. {exercise}: {sets}x{reps}@{weight}\n"

    print(f"✅ Built general context")
    conn.close()
    return context_info
