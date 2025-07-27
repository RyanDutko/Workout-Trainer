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
cursor.execute('INSERT OR IGNORE INTO users (id, goal, weekly_split, preferences) VALUES (1, "", "", "")')
conn.commit()

# Fuzzy match for typo tolerance
def is_similar(text1, text2, threshold=0.8):
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio() > threshold

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

# Local regex-based parser for workouts
def call_grok_parse(user_input, date_logged):
    match = re.search(r'(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)(lbs|kg)?\s*([\w\s]+)', user_input.lower().rstrip())
    if match:
        sets, reps, weight, unit, exercise = match.groups()
        if not unit: unit = "lbs"
        return {
            "exercise_name": exercise.strip(),
            "sets": int(sets),
            "reps": reps,
            "weight": f"{weight}{unit}",
            "notes": ""
        }
    return None

# Insert workout log into database with debug
def insert_log(entry, date_logged):
    if not entry:
        return
    if isinstance(entry, list):
        for single_entry in entry:
            print(f"Inserting: {single_entry}")
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
            conn.commit()
            print(f"✅ Logged: {single_entry['exercise_name']} - {single_entry['sets']}x{single_entry['reps']}@{single_entry['weight']} on {date_logged}")
    else:
        print(f"Inserting: {entry}")
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
        conn.commit()
        print(f"✅ Logged: {entry['exercise_name']} - {entry['sets']}x{entry['reps']}@{entry['weight']} on {date_logged}")

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
    for row in rows[:10]:
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

# Get response from Grok API
def get_grok_response(prompt):
    client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
    try:
        response = client.chat.completions.create(
            model="grok-4-0709",
            messages=[{"role": "system", "content": "You are a helpful personal trainer AI."}, {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"⚠️ API error in get_grok_response: {str(e)}")
        return "I'm here to help! Log a workout, ask for history, or request progression tips."

# Progression tips with Grok API
def get_progression_tips(user_input):
    cursor.execute("SELECT goal, weekly_split FROM users WHERE id = 1")
    user_profile = cursor.fetchone()
    goal, weekly_split = user_profile if user_profile else ("", "")

    cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    cursor.execute("SELECT exercise_name, sets, reps, weight, date_logged FROM workouts WHERE date_logged>=? ORDER BY date_logged", (cutoff,))
    rows = cursor.fetchall()
    if not rows:
        print("⚠️ No logs to analyze for progression.")
        return
    text = user_input.lower()
    last_days = None
    if "last" in text:
        match = re.search(r"last (\d+) days", text)
        if match:
            last_days = int(match.group(1))
    exercise = None
    if not any(x in text for x in ["my last", "whole week"]):
        exercise = " ".join(text.split()[-2:]).strip()
    history = {}
    today = datetime.date.today()
    # Map exercises to split days
    split_days = {day.split(':')[0].strip(): day.split(':')[1].strip() for day in weekly_split.split(',') if ':' in day} if weekly_split else {}
    muscle_to_day = {}
    for day, muscles in split_days.items():
        for muscle in muscles.split(' and '):
            muscle_to_day[muscle.strip().lower()] = day.capitalize()
    for row in rows:
        name, sets, reps, weight, date = row
        try:
            row_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
            if last_days and (row_date < today - datetime.timedelta(days=last_days) or row_date > today):
                continue
        except ValueError:
            continue
        if name.lower() not in history:
            history[name.lower()] = []
        history[name.lower()].append(f"[{date}] {name}: {sets}x{reps}@{weight}")
    if not history:
        print("⚠️ No valid logs found for progression.")
        return
    client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
    tips = []
    for ex, logs in history.items():
        if exercise and ex != exercise:
            continue
        # Find best matching split day
        split_day = None
        for muscle, day in muscle_to_day.items():
            if muscle in ex:
                split_day = day
                break
        prompt = f"You are a personal trainer. User goal: {goal}. Weekly split: {weekly_split}. Based on this workout history for {ex}: {', '.join(logs)}, provide a concise progression tip (e.g., 'Try 205lbs for 2x8'). Mention the split day ({split_day}) if applicable. Keep it short, no explanations unless asked."
        try:
            response = client.chat.completions.create(
                model="grok-4-0709",
                messages=[{"role": "system", "content": "You are a helpful personal trainer AI."}, {"role": "user", "content": prompt}],
                temperature=0.7
            )
            tip = response.choices[0].message.content
            if split_day:
                tip = f"{split_day}: {tip}"
            tips.append(f"For {ex}: {tip}")
        except Exception as e:
            tip = f"⚠️ API error: {e}. Try increasing weight by 5-10lbs or reps by 1-2."
            if split_day:
                tip = f"{split_day}: {tip}"
            tips.append(f"For {ex}: {tip}")
    if not tips:
        print(f"⚠️ No logs found for {exercise}." if exercise else "⚠️ No valid logs found.")
        return
    print("\n🤖 Progression Tips:\n" + "\n".join(tips))

# Store last 3 interactions for context
conversation_history = []



import os
import sqlite3
import datetime
import re
from dateutil import parser as date_parser
from openai import OpenAI

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
cursor.execute('INSERT OR IGNORE INTO users (id, goal, weekly_split, preferences) VALUES (1, "", "", "")')
conn.commit()

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
    if any(x in text for x in ["set my goal", "weekly split", "my split"]):
        return "profile"
    if any(x in text for x in ["why", "don't want", "dont want", "replace", "instead", "swap", "another workout"]) and conversation_history:
        return "follow-up"
    if any(x in text for x in ["progression", "suggest", "tips", "next"]) and not any(x in text for x in ["replace", "another workout"]):
        return "progression"
    if any(x in text for x in ["show", "history", "what did i do", "logs"]):
        return "query"
    return "chat"

# Local regex-based parser for workouts
def call_grok_parse(user_input, date_logged):
    match = re.search(r'(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)(lbs|kg)?\s*([\w\s]+)', user_input.lower().rstrip())
    if match:
        sets, reps, weight, unit, exercise = match.groups()
        if not unit: unit = "lbs"
        return {
            "exercise_name": exercise.strip(),
            "sets": int(sets),
            "reps": reps,
            "weight": f"{weight}{unit}",
            "notes": ""
        }
    return None

# Insert workout log into database with debug
def insert_log(entry, date_logged):
    if not entry:
        return
    if isinstance(entry, list):
        for single_entry in entry:
            print(f"Inserting: {single_entry}")
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
            conn.commit()
            print(f"✅ Logged: {single_entry['exercise_name']} - {single_entry['sets']}x{single_entry['reps']}@{single_entry['weight']} on {date_logged}")
    else:
        print(f"Inserting: {entry}")
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
        conn.commit()
        print(f"✅ Logged: {entry['exercise_name']} - {entry['sets']}x{entry['reps']}@{entry['weight']} on {date_logged}")

# Update user profile
def update_profile(user_input):
    text = user_input.lower()
    if "set my goal" in text:
        goal = re.sub(r'set my goal to', '', text).strip()
        cursor.execute('UPDATE users SET goal = ? WHERE id = 1', (goal,))
        conn.commit()
        return f"Goal set to: {goal}"
    if "weekly split" in text or "my split" in text:
        split = re.sub(r'my weekly split is|weekly split', '', text).strip()
        cursor.execute('UPDATE users SET weekly_split = ? WHERE id = 1', (split,))
        conn.commit()
        return f"Weekly split set to: {split}"
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
    for row in rows[:10]:
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

# Get response from Grok API
def get_grok_response(prompt):
    client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
    try:
        response = client.chat.completions.create(
            model="grok-4-0709",
            messages=[{"role": "system", "content": "You are a helpful personal trainer AI."}, {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"⚠️ API error in get_grok_response: {str(e)}")
        return "I'm here to help! Log a workout, ask for history, or request progression tips."

# Progression tips with Grok API
def get_progression_tips(user_input):
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    cursor.execute("SELECT exercise_name, sets, reps, weight, date_logged FROM workouts WHERE date_logged>=? ORDER BY date_logged", (cutoff,))
    rows = cursor.fetchall()
    if not rows:
        print("⚠️ No logs to analyze for progression.")
        return
    text = user_input.lower()
    last_days = None
    if "last" in text:
        match = re.search(r"last (\d+) days", text)
        if match:
            last_days = int(match.group(1))
    exercise = None
    if not any(x in text for x in ["my last", "whole week"]):
        exercise = " ".join(text.split()[-2:]).strip()
    history = {}
    today = datetime.date.today()
    for row in rows:
        name, sets, reps, weight, date = row
        try:
            row_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
            if last_days and (row_date < today - datetime.timedelta(days=last_days) or row_date > today):
                continue
        except ValueError:
            continue
        if name.lower() not in history:
            history[name.lower()] = []
        history[name.lower()].append(f"[{date}] {name}: {sets}x{reps}@{weight}")
    if not history:
        print("⚠️ No valid logs found for progression.")
        return
    client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
    tips = []
    for ex, logs in history.items():
        if exercise and ex != exercise:
            continue
        prompt = f"You are a personal trainer. User goal: {goal}. Weekly split: {weekly_split}. Based on this workout history for {ex}: {', '.join(logs)}, provide a concise progression tip (e.g., 'Try 205lbs for 2x8'). Keep it short, no explanations unless asked."
        try:
            response = client.chat.completions.create(
                model="grok-4-0709",
                messages=[{"role": "system", "content": "You are a helpful personal trainer AI."}, {"role": "user", "content": prompt}],
                temperature=0.7
            )
            tips.append(f"For {ex}: {response.choices[0].message.content}")
        except Exception as e:
            tips.append(f"For {ex}: ⚠️ API error: {e}. Try increasing weight by 5-10lbs or reps by 1-2.")
    if not tips:
        print(f"⚠️ No logs found for {exercise}." if exercise else "⚠️ No valid logs found.")
        return
    print("\n🤖 Progression Tips:\n" + "\n".join(tips))

# Store last 3 interactions for context
conversation_history = []

print("\n💪 Grok Personal Trainer: Log workouts, view history, or ask for tips. Type 'done' to exit.")
print("Example: '3x10@200 bench press' or 'Show last 7 days' or 'Suggest progression for bench press'\n")
while True:
    try:
        user_input = input("🗣️ You: ").strip()
        if user_input.lower() == "done":
            break

        intent = detect_intent(user_input)
        print(f"Detected intent: {intent}")
        date_logged = extract_date(user_input)

        # Prepare context for Grok
        context = "\n".join([f"User: {h['input']}\nApp: {h['response']}" for h in conversation_history[-2:]])
        if context:
            context = f"Previous conversation:\n{context}\n\n"

        if intent == "log":
            entry = call_grok_parse(user_input, date_logged)
            if entry:
                insert_log(entry, date_logged)
                response = f"Logged your {entry['exercise_name']} workout!"
            else:
                prompt = f"{context}Parse this workout log into JSON: exercise_name, sets (int), reps (string), weight (string, use 'Body' if no weight specified), notes (string, exclude any date phrases like 'yesterday' or 'two days ago'). Input: {user_input}"
                response = get_grok_response(prompt)
                try:
                    entry = eval(response.strip())
                    insert_log(entry, date_logged)
                    response = f"Logged your workout(s)!"
                except:
                    response = "⚠️ Couldn't parse with Grok. Try a clearer format."
        elif intent == "log-prep":
            prompt = f"{context}You are a personal trainer. Respond concisely to: {user_input}"
            response = get_grok_response(prompt)
            print(f"🤖 Grok: {response}")
        elif intent == "query":
            show_logs(user_input)
            response = "Displayed your logs."
        elif intent == "progression":
            get_progression_tips(user_input)
            response = "Suggested progression tips."
        elif intent == "profile":
            response = update_profile(user_input)
            print(f"🤖 Grok: {response}")
        elif intent == "follow-up":
            prompt = f"{context}You are a personal trainer. Respond concisely to this follow-up about recent advice, referencing the specific tip if applicable (e.g., acknowledge preferences, suggest replacements with sets/reps, no long details unless asked): {user_input}"
            response = get_grok_response(prompt)
            print(f"🤖 Grok: {response}")
        else:
            prompt = f"{context}You are a personal trainer. Respond naturally and concisely to: {user_input}"
            response = get_grok_response(prompt)
            print(f"🤖 Grok: {response}")

        conversation_history.append({"input": user_input, "response": response})
        if len(conversation_history) > 3:
            conversation_history.pop(0)
    except Exception as e:
        print(f"⚠️ Main loop error: {str(e)}")
conn.close()