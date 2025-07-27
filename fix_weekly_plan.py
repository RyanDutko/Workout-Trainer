
import sqlite3
import re

conn = sqlite3.connect('workout_logs.db')
cursor = conn.cursor()

# Clear the malformed weekly plan
cursor.execute("DELETE FROM weekly_plan")
print("Cleared malformed weekly plan")

# Your original input, but properly structured
weekly_data = {
    'monday': [
        'seated leg curl 3x12@85lbs',
        'leg press 3x12@180lbs', 
        'leg extensions 3x12@80lbs',
        'glute slide machine 3x12@70lbs',
        'glute abduction 3x12@130lbs',
        'adductor machine 3x12@130lbs'
    ],
    'tuesday': [
        'plate loaded chest press 3x12@90lbs',
        'incline dumbbell press 3x12@35lbs',
        'tricep rope pushdown 3x12@30lbs',
        'lower to upper cable chest flys 3x12@20lbs',
        'upper to lower cable chest flys 3x12@20lbs',
        'heavy low to high cable chest flys 3x12@30lbs',
        'straight bar pushdowns 3x12@40lbs'
    ],
    'wednesday': [
        'assisted pull ups 3x12@90lbs',
        'chest supported row 3x12@100lbs',
        'cable woodchops 3x12@40lbs',
        'seated back extension 3x15@110lbs',
        'cable lateral raises 3x12@20lbs',
        'strap ab crunch 3x12@50lbs',
        'optional ab burnout 3x12@bodyweight'
    ],
    'thursday': [
        'rear delt fly 3x15@80lbs',
        'dumbbell lateral raises 3x12@15lbs',
        'seated arnold press 3x12@20lbs',
        'hammer curls 3x12@25lbs',
        'cable preacher curl 3x12@20lbs',
        'bicep finisher rounds 2x40@15lbs',
        'cable front raises 2x12@20lbs'
    ],
    'friday': [
        'goblet split squats 3x12@35lbs',
        'elevated pushups 3x20@bodyweight',
        'chest supported row 3x12@100lbs',
        'cable woodchops 3x10@45lbs',
        'seated back extension 3x15@110lbs',
        'strap ab crunch 3x12@50lbs',
        'cable lateral raises 3x12@20lbs',
        'machine bicep curl 3x12@70lbs',
        'glute drive 3x12@90lbs'
    ]
}

# Insert each day's exercises properly
for day, exercises in weekly_data.items():
    order = 1
    for exercise_text in exercises:
        # Parse exercise: "exercise name 3x12@180lbs"
        pattern = r'(.+?)\s+(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)\s*(lbs|kg|bodyweight)?'
        match = re.search(pattern, exercise_text.strip())
        
        if match:
            exercise_name, sets, reps, weight, unit = match.groups()
            if not unit:
                unit = "lbs"
            weight_with_unit = f"{weight}{unit}" if unit != "bodyweight" else "bodyweight"
            
            cursor.execute('''
                INSERT INTO weekly_plan 
                (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, created_date, updated_date)
                VALUES (?, ?, ?, ?, ?, ?, date('now'), date('now'))
            ''', (day, exercise_name.strip(), int(sets), reps, weight_with_unit, order))
            
            print(f"✅ Added: {day} - {exercise_name.strip()} {sets}x{reps}@{weight_with_unit}")
            order += 1
        else:
            print(f"⚠️ Couldn't parse: {exercise_text}")

conn.commit()

# Show the corrected weekly plan
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

plan = cursor.fetchall()
print("\n📋 Corrected Weekly Plan:")
current_day = ""
for row in plan:
    day, exercise, sets, reps, weight, order = row
    if day != current_day:
        print(f"\n🔸 {day.title()}:")
        current_day = day
    print(f"  {order}. {exercise}: {sets}x{reps}@{weight}")

conn.close()
