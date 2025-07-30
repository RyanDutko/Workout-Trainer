
import sqlite3

def debug_database():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    print("=== WORKOUT LOGS ===")
    cursor.execute('SELECT id, exercise_name, sets, reps, weight, date_logged FROM workouts ORDER BY date_logged DESC')
    workouts = cursor.fetchall()
    for workout in workouts:
        print(f"ID: {workout[0]}, Exercise: {workout[1]}, Sets: {workout[2]}, Reps: {workout[3]}, Weight: {workout[4]}, Date: {workout[5]}")
    
    print(f"\nTotal workout logs: {len(workouts)}")
    
    print("\n=== WEEKLY PLAN ===")
    cursor.execute('SELECT id, exercise_name, newly_added, created_by, day_of_week FROM weekly_plan ORDER BY day_of_week, exercise_order')
    plan_exercises = cursor.fetchall()
    for exercise in plan_exercises:
        print(f"ID: {exercise[0]}, Exercise: {exercise[1]}, New: {exercise[2]}, Created by: {exercise[3]}, Day: {exercise[4]}")
    
    print(f"\nTotal plan exercises: {len(plan_exercises)}")
    
    # Check specifically for Roman Chair Back Extension
    print("\n=== ROMAN CHAIR BACK EXTENSION CHECK ===")
    cursor.execute('SELECT COUNT(*) FROM workouts WHERE LOWER(exercise_name) LIKE "%roman chair%"')
    roman_logs = cursor.fetchone()[0]
    print(f"Roman Chair workout logs: {roman_logs}")
    
    cursor.execute('SELECT newly_added, created_by FROM weekly_plan WHERE LOWER(exercise_name) LIKE "%roman chair%"')
    roman_plan = cursor.fetchone()
    if roman_plan:
        print(f"Roman Chair in plan - New: {roman_plan[0]}, Created by: {roman_plan[1]}")
    else:
        print("Roman Chair not found in weekly plan")
    
    conn.close()

if __name__ == "__main__":
    debug_database()
