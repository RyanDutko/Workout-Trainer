import sqlite3

conn = sqlite3.connect('workout_logs.db')
cursor = conn.cursor()
cursor.execute('DELETE FROM workouts WHERE date_logged < "2025-01-01" OR date_logged > "2025-12-31"')
conn.commit()
cursor.execute('SELECT * FROM workouts')
print(cursor.fetchall())
conn.close()