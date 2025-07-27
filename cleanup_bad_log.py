
import sqlite3

conn = sqlite3.connect('workout_logs.db')
cursor = conn.cursor()

# Delete the malformed log entry that has exercises in the exercise_name field
cursor.execute("DELETE FROM workouts WHERE exercise_name LIKE '%lbs, leg press%'")
deleted_rows = cursor.rowcount

conn.commit()

print(f"Deleted {deleted_rows} malformed log entries")

# Show remaining logs to verify
cursor.execute('SELECT id, exercise_name, sets, reps, weight, date_logged FROM workouts ORDER BY date_logged DESC LIMIT 10')
rows = cursor.fetchall()
print("\nRemaining recent logs:")
for row in rows:
    print(row)

conn.close()
