import sqlite3

try:
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    print('Connected to database successfully')
    
    cursor.execute('SELECT exercise_name, target_sets, target_reps, target_weight FROM weekly_plan WHERE day_of_week = "tuesday" ORDER BY exercise_order')
    exercises = cursor.fetchall()
    
    print('Current Tuesday plan:')
    if exercises:
        for exercise in exercises:
            print(f'  {exercise[0]}: {exercise[1]}x{exercise[2]}@{exercise[3]}')
    else:
        print('  No exercises found for Tuesday')
    
    # Also check all days to see what's in the plan
    cursor.execute('SELECT day_of_week, COUNT(*) FROM weekly_plan GROUP BY day_of_week')
    day_counts = cursor.fetchall()
    print('\nPlan summary by day:')
    for day, count in day_counts:
        print(f'  {day}: {count} exercises')
    
    conn.close()
    print('Database connection closed')
    
except Exception as e:
    print(f'Error: {e}')
