import os
import sqlite3
import datetime
import re
from dateutil import parser as date_parser
from openai import OpenAI
from difflib import SequenceMatcher

# Initialize SQLite database
DB_PATH = "workout_logs.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_name TEXT,
    sets INTEGER,
    reps TEXT,
    weight TEXT,
    date_logged TEXT,
    notes TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal TEXT,
    weekly_split TEXT,
    preferences TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS exercise_progression (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_name TEXT,
    last_weight REAL,
    last_reps INTEGER,
    last_sets INTEGER,
    progression_rate REAL DEFAULT 2.5,
    updated_date TEXT
)
''')

cursor.execute('INSERT OR IGNORE INTO users (id, goal, weekly_split, preferences) VALUES (1, "", "", "")')
conn.commit()

# Fuzzy match for typo tolerance
def is_similar(text1, text2, threshold=0.8):
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio() > threshold

# Get user profile
def get_user_profile():
    cursor.execute("SELECT goal, weekly_split, preferences FROM users WHERE id = 1")
    result = cursor.fetchone()
    return result if result else ("", "", "")

# Extract numeric weight for progression calculations
def extract_weight_number(weight_str):
    match = re.search(r'(\d+\.?\d*)', str(weight_str))
    return float(match.group(1)) if match else 0

# Update exercise progression tracking
def update_progression_data(exercise_name, sets, reps, weight):
    weight_num = extract_weight_number(weight)
    reps_num = int(reps.split('-')[0]) if '-' in str(reps) else int(reps)

    cursor.execute('''
        INSERT OR REPLACE INTO exercise_progression 
        (exercise_name, last_weight, last_reps, last_sets, updated_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (exercise_name.lower(), weight_num, reps_num, sets, datetime.date.today().isoformat()))
    conn.commit()

# Calculate local progression suggestion
def calculate_local_progression(exercise_name):
    cursor.execute('''
        SELECT last_weight, last_reps, last_sets, progression_rate 
        FROM exercise_progression 
        WHERE exercise_name = ?
    ''', (exercise_name.lower(),))

    result = cursor.fetchone()
    if not result:
        return None

    last_weight, last_reps, last_sets, progression_rate = result

    # Simple progression logic
    if last_reps >= 12:  # If hitting high reps, increase weight
        new_weight = last_weight + progression_rate
        new_reps = max(8, last_reps - 2)
        return f"Try {new_weight}lbs for {last_sets}x{new_reps}"
    elif last_reps < 6:  # If struggling with reps, reduce weight slightly
        new_weight = max(last_weight - progression_rate, last_weight * 0.9)
        new_reps = last_reps + 2
        return f"Try {new_weight}lbs for {last_sets}x{new_reps}"
    else:  # Add reps or sets
        if last_reps < 10:
            return f"Try adding 1-2 reps: {last_weight}lbs for {last_sets}x{last_reps + 1}-{last_reps + 2}"
        else:
            return f"Try adding a set: {last_weight}lbs for {last_sets + 1}x{last_reps}"

# Detect date from input
def extract_date(user_input):
    today = datetime.date.today()
    user_input = user_input.lower()
    if "yesterday" in user_input:
        return today - datetime.timedelta(days=1)
    if "last week" in user_input:
        return today - datetime.timedelta(days=7)
    match_days_ago = re.search(r'(\d+)\s*days?\s*ago', user_input)
    if match_days_ago:
        days = int(match_days_ago.group(1))
        return today - datetime.timedelta(days=days)
    try:
        if any(keyword in user_input for keyword in ['on ', 'date']):
            parsed_date = date_parser.parse(user_input, fuzzy=True, dayfirst=False).date()
            if parsed_date <= today:
                return parsed_date
    except:
        pass
    return today

# Detect intent of user input
def detect_intent(user_input):
    text = user_input.lower()
    if any(x in text for x in ["did", "sets", "reps", "lbs", "kg", "press", "squat", "kettlebell"]) and re.search(r'\d+', text):
        return "log"
    if any(x in text for x in ["ready to log", "here is my log", "full log"]):
        return "log-prep"
    if any(x in text for x in ["set my goal", "weekly split", "my split", "what's my goal", "show my goal"]) or is_similar(text, "show my split", 0.8):
        return "profile"
    if any(x in text for x in ["why", "don't want", "dont want", "replace", "instead", "swap", "another workout"]) and conversation_history:
        return "follow-up"
    if any(x in text for x in ["progression", "suggest", "tips", "next"]) and not any(x in text for x in ["replace", "another workout"]):
        return "progression"
    if any(x in text for x in ["show", "history", "what did i do", "logs"]) and not is_similar(text, "show my split", 0.8):
        return "query"
    return "chat"

# Enhanced regex parser for workouts
def call_grok_parse(user_input, date_logged):
    # Try multiple patterns
    patterns = [
        r'(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)(lbs|kg)?\s*(.*)',  # 3x10@200lbs bench press
        r'(\d+)\s*sets?\s*of\s*(\d+|\d+-\d+)\s*(?:reps?\s*)?(?:at|@)\s*(\d+\.?\d*)(lbs|kg)?\s*(.*)',  # 3 sets of 10 at 200lbs bench press
        r'(.*?)\s*(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)(lbs|kg)?',  # bench press 3x10@200lbs
    ]

    for pattern in patterns:
        match = re.search(pattern, user_input.lower().strip())
        if match:
            if len(match.groups()) == 5:  # Standard format
                sets, reps, weight, unit, exercise = match.groups()
            else:  # Alternative format
                exercise, sets, reps, weight, unit = match.groups()

            if not unit: 
                unit = "lbs"

            exercise_name = exercise.strip()
            if not exercise_name:
                exercise_name = "Unknown Exercise"

            return {
                "exercise_name": exercise_name,
                "sets": int(sets),
                "reps": reps,
                "weight": f"{weight}{unit}",
                "notes": ""
            }
    return None

# Insert workout log into database with progression tracking
def insert_log(entry, date_logged):
    if not entry:
        return

    if isinstance(entry, list):
        for single_entry in entry:
            cursor.execute('''
                INSERT INTO workouts (exercise_name, sets, reps, weight, date_logged, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                single_entry.get("exercise_name", "Unknown"),
                single_entry.get("sets", 1),
                single_entry.get("reps", "Unknown"),
                single_entry.get("weight", "0"),
                date_logged.isoformat(),
                single_entry.get("notes", "")
            ))

            # Update progression tracking
            update_progression_data(
                single_entry.get("exercise_name", "Unknown"),
                single_entry.get("sets", 1),
                single_entry.get("reps", "Unknown"),
                single_entry.get("weight", "0")
            )

            print(f"✅ Logged: {single_entry['exercise_name']} - {single_entry['sets']}x{single_entry['reps']}@{single_entry['weight']} on {date_logged}")
    else:
        cursor.execute('''
            INSERT INTO workouts (exercise_name, sets, reps, weight, date_logged, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            entry.get("exercise_name", "Unknown"),
            entry.get("sets", 1),
            entry.get("reps", "Unknown"),
            entry.get("weight", "0"),
            date_logged.isoformat(),
            entry.get("notes", "")
        ))

        # Update progression tracking
        update_progression_data(
            entry.get("exercise_name", "Unknown"),
            entry.get("sets", 1),
            entry.get("reps", "Unknown"),
            entry.get("weight", "0")
        )

        print(f"✅ Logged: {entry['exercise_name']} - {entry['sets']}x{entry['reps']}@{entry['weight']} on {date_logged}")

    conn.commit()

# Update or show user profile
def update_profile(user_input):
    text = user_input.lower()
    if "set my goal" in text:
        goal = re.sub(r'set my goal to', '', text).strip()
        cursor.execute('UPDATE users SET goal = ? WHERE id = 1', (goal,))
        conn.commit()
        return f"Goal set to: {goal}"
    if "weekly split" in text or "my split" in text and "set" in text or "update" in text:
        split = re.sub(r'my weekly split is|weekly split', '', text).strip()
        cursor.execute('UPDATE users SET weekly_split = ? WHERE id = 1', (split,))
        conn.commit()
        return f"Weekly split set to: {split}"
    if "what's my goal" in text or "show my goal" in text:
        cursor.execute("SELECT goal FROM users WHERE id = 1")
        goal = cursor.fetchone()[0]
        return f"Your goal is: {goal if goal else 'not set'}"
    if "show my split" in text or is_similar(text, "show my split", 0.8):
        cursor.execute("SELECT weekly_split FROM users WHERE id = 1")
        split = cursor.fetchone()[0]
        return f"Your weekly split is: {split if split else 'not set'}"
    return "⚠️ Couldn't update profile. Try 'set my goal to build muscle' or 'my weekly split is Monday: chest'."

# Retrieve logs for display
def show_logs(user_input):
    today = datetime.date.today()
    last_days = None
    if "last" in user_input.lower():
        match = re.search(r"last (\d+) days", user_input.lower())
        if match:
            last_days = int(match.group(1))

    date_logged = extract_date(user_input)
    cursor.execute("SELECT exercise_name, sets, reps, weight, date_logged, notes FROM workouts ORDER BY date_logged DESC")
    rows = cursor.fetchall()

    if not rows:
        print("⚠️ No logs found.")
        return

    print("\n📋 Workout Logs:")
    displayed = False
    for row in rows[:20]:  # Show more logs
        name, sets, reps, weight, date, notes = row
        try:
            row_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
            if last_days:
                cutoff = today - datetime.timedelta(days=last_days)
                if row_date >= cutoff and row_date <= today:
                    print(f"[{date}] {name}: {sets}x{reps}@{weight} {('- ' + notes) if notes else ''}")
                    displayed = True
            elif row_date == date_logged:
                print(f"[{date}] {name}: {sets}x{reps}@{weight} {('- ' + notes) if notes else ''}")
                displayed = True
        except ValueError:
            continue

    if not displayed:
        print("⚠️ No logs found for the specified period.")

# Get response from Grok API with context
def get_grok_response(prompt, include_context=True):
    client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")

    if include_context:
        # Add user profile and recent workout context
        goal, weekly_split, preferences = get_user_profile()
        context_info = f"\nUser Profile - Goal: {goal}, Weekly Split: {weekly_split}"

        # Add recent workouts for context
        cursor.execute("SELECT exercise_name, sets, reps, weight, date_logged FROM workouts ORDER BY date_logged DESC LIMIT 10")
        recent_workouts = cursor.fetchall()
        if recent_workouts:
            context_info += "\nRecent Workouts: " + "; ".join([f"{w[0]} {w[1]}x{w[2]}@{w[3]} ({w[4]})" for w in recent_workouts[:5]])

        prompt = context_info + "\n\n" + prompt

    try:
        response = client.chat.completions.create(
            model="grok-4-0709",
            messages=[{"role": "system", "content": "You are a helpful personal trainer AI with access to the user's workout history and profile."}, {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"⚠️ API error: {str(e)}")
        return "I'm here to help! Log a workout, ask for history, or request progression tips."

# Enhanced progression tips with local calculations
def get_progression_tips(user_input):
    goal, weekly_split, preferences = get_user_profile()

    # Extract specific exercise from user input
    text = user_input.lower()
    exercise_name = None

    # Try to find exercise name in input
    words = text.split()
    for i, word in enumerate(words):
        if word in ["for", "progression", "suggest"]:
            if i + 1 < len(words):
                exercise_name = " ".join(words[i + 1:]).strip()
                break

    if not exercise_name:
        # Look for common exercise names
        common_exercises = ["squat", "bench", "deadlift", "press", "row", "curl", "pullup", "pull up"]
        for exercise in common_exercises:
            if exercise in text:
                exercise_name = exercise
                break

    if exercise_name:
        # Try local progression first
        local_suggestion = calculate_local_progression(exercise_name)
        if local_suggestion:
            print(f"\n🤖 Local Progression Suggestion for {exercise_name}:")
            print(local_suggestion)
            return

        # Fall back to database lookup for similar exercises
        cursor.execute('''
            SELECT exercise_name, sets, reps, weight, date_logged 
            FROM workouts 
            WHERE LOWER(exercise_name) LIKE ? 
            ORDER BY date_logged DESC LIMIT 5
        ''', (f'%{exercise_name}%',))

        matching_exercises = cursor.fetchall()
        if matching_exercises:
            print(f"\n🤖 Progression Tips for exercises containing '{exercise_name}':")
            for ex in matching_exercises:
                name, sets, reps, weight, date = ex
                local_suggestion = calculate_local_progression(name)
                if local_suggestion:
                    print(f"• {name}: {local_suggestion}")
                else:
                    print(f"• {name}: Try increasing weight by 2.5-5lbs or adding 1-2 reps")
            return

    # If no specific exercise found, show general progression for all recent exercises
    cursor.execute('''
        SELECT DISTINCT exercise_name 
        FROM workouts 
        WHERE date_logged >= date('now', '-30 days')
    ''')
    recent_exercises = [row[0] for row in cursor.fetchall()]

    if recent_exercises:
        print("\n🤖 Progression Tips for Recent Exercises:")
        for exercise in recent_exercises[:5]:  # Limit to avoid too many API calls
            local_suggestion = calculate_local_progression(exercise)
            if local_suggestion:
                print(f"• {exercise}: {local_suggestion}")
    else:
        print("⚠️ No recent workout data found for progression analysis.")

# Store last 3 interactions for context
conversation_history = []

print("\n💪 Enhanced Personal Trainer: Log workouts, view history, or ask for tips. Type 'done' to exit.")
print("Example: '3x10@200 bench press' or 'Show last 7 days' or 'Suggest progression for squats'\n")

while True:
    try:
        user_input = input("🗣️ You: ").strip()
        if user_input.lower() == "done":
            break

        intent = detect_intent(user_input)
        print(f"Detected intent: {intent}")
        date_logged = extract_date(user_input)

        # Prepare context for Grok (only recent conversation)
        context = "\n".join([f"User: {h['input']}\nApp: {h['response']}" for h in conversation_history[-2:]])
        if context:
            context = f"Previous conversation:\n{context}\n\n"

        if intent == "log":
            entry = call_grok_parse(user_input, date_logged)
            if entry:
                insert_log(entry, date_logged)
                response = f"Logged your {entry['exercise_name']} workout!"
            else:
                # Only use API if local parsing fails
                prompt = f"{context}Parse this workout log into JSON format with keys: exercise_name, sets (int), reps (string), weight (string with units), notes (string). Input: {user_input}"
                api_response = get_grok_response(prompt, include_context=False)
                try:
                    # Try to extract JSON from response
                    import json
                    entry = json.loads(api_response.strip())
                    insert_log(entry, date_logged)
                    response = f"Logged your workout via API parsing!"
                except:
                    response = "⚠️ Couldn't parse workout. Try format like '3x10@200lbs bench press'"

        elif intent == "query":
            show_logs(user_input)
            response = "Displayed your logs."

        elif intent == "progression":
            get_progression_tips(user_input)
            response = "Provided progression suggestions."

        elif intent == "profile":
            response = update_profile(user_input)
            print(f"🤖 Profile: {response}")

        elif intent == "follow-up":
            prompt = f"{context}Respond as a personal trainer to this follow-up question: {user_input}"
            response = get_grok_response(prompt)
            print(f"🤖 Trainer: {response}")

        else:
            prompt = f"{context}Respond naturally as a personal trainer to: {user_input}"
            response = get_grok_response(prompt)
            print(f"🤖 Trainer: {response}")

        # Store conversation for context
        conversation_history.append({"input": user_input, "response": response[:100]})  # Truncate long responses
        if len(conversation_history) > 3:
            conversation_history.pop(0)

    except Exception as e:
        print(f"⚠️ Error: {str(e)}")

conn.close()