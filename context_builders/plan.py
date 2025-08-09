
import sqlite3

def build_plan_context():
    """Build context for weekly plan queries - ONLY plan data"""
    print("🔍 Building plan context")
    
    conn = sqlite3.connect('workout_logs.db')
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
    weekly_plan = cursor.fetchall()
    
    if weekly_plan:
        context_info = "\n=== YOUR WEEKLY WORKOUT PLAN ===\n"
        current_day = ""
        for row in weekly_plan:
            day, exercise, sets, reps, weight, order = row
            if day != current_day:
                if current_day:
                    context_info += "\n"
                context_info += f"\n{day.upper()}:\n"
                current_day = day
            context_info += f"  {order}. {exercise}: {sets}x{reps}@{weight}\n"
        
        print(f"✅ Built plan context with {len(set(row[0] for row in weekly_plan))} days")
        conn.close()
        return context_info
    else:
        print("❌ No weekly plan found")
        conn.close()
        return "\n=== NO WEEKLY PLAN SET ===\n"
