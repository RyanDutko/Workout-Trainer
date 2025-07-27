import sqlite3

conn = sqlite3.connect('workout_logs.db')
cursor = conn.cursor()
cursor.execute('DELETE FROM workouts WHERE id = 8')
conn.commit()
cursor.execute('SELECT id, exercise_name, sets, reps, weight, date_logged, notes FROM workouts')
rows = cursor.fetchall()
for row in rows:
    print(row)
conn.close()