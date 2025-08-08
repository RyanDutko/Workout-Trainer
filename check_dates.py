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
    SELECT exercise_name, sets, reps, weight, date_logged, notes
    FROM workouts
    WHERE strftime('%w', date_logged) = '2'
    ORDER BY date_logged DESC
""")
results = cursor.fetchall()
if results:
    print(f"Found {len(results)} Tuesday workout logs:")
    for r in results:
        print(f"{r[4]} – {r[0]}: {r[1]}x{r[2]}@{r[3]}")
        if r[5]:  # notes
            print(f"  Notes: {r[5][:100]}...")
else:
    print("No Tuesday logs found.")

print("\nTesting specific day detection...")
test_prompts = [
    "show me my most recent tuesday logs",
    "what did I do on Tuesday", 
    "my tuesday workout"
]

for prompt in test_prompts:
    for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
        if day in prompt.lower():
            print(f"'{prompt}' -> detected day: {day}")
            break

conn.close()
