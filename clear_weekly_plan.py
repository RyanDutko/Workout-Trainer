
import sqlite3

conn = sqlite3.connect('workout_logs.db')
cursor = conn.cursor()

# Delete all weekly plan entries
cursor.execute("DELETE FROM weekly_plan")
deleted_rows = cursor.rowcount

conn.commit()

print(f"Deleted {deleted_rows} weekly plan entries")

# Verify it's empty
cursor.execute('SELECT COUNT(*) FROM weekly_plan')
count = cursor.fetchone()[0]
print(f"Weekly plan now has {count} entries")

conn.close()
