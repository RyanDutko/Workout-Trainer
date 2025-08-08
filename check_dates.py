import sqlite3

conn = sqlite3.connect("workout_logs.db")
cursor = conn.cursor()

# Check how your date_logged values are stored
print("Recent date_logged values:")
cursor.execute("SELECT DISTINCT date_logged FROM workouts ORDER BY date_logged DESC LIMIT 10;")
for row in cursor.fetchall():
    print(row[0])

print("\nNow checking for Tuesday logs...")
cursor.execute("""
    SELECT exercise_name, date_logged
    FROM workouts
    WHERE strftime('%w', date_logged) = '2'
    ORDER BY date_logged DESC
""")
results = cursor.fetchall()
if results:
    for r in results:
        print(f"{r[1]} – {r[0]}")
else:
    print("No Tuesday logs found.")

conn.close()
