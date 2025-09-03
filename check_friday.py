import sqlite3

conn = sqlite3.connect('workout_logs.db')
cursor = conn.cursor()

cursor.execute('SELECT exercise_name, target_sets, target_reps, target_weight FROM weekly_plan WHERE day_of_week = "friday" ORDER BY exercise_order')
exercises = cursor.fetchall()

print('Current Friday plan:')
if exercises:
    for exercise in exercises:
        print(f'  {exercise[0]}: {exercise[1]}x{exercise[2]}@{exercise[3]}')
else:
    print('  No exercises found for Friday')

conn.close()

