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
    preferences TEXT,
    grok_tone TEXT DEFAULT 'motivational',
    grok_detail_level TEXT DEFAULT 'concise',
    grok_format TEXT DEFAULT 'bullet_points',
    preferred_units TEXT DEFAULT 'lbs',
    communication_style TEXT DEFAULT 'encouraging',
    technical_level TEXT DEFAULT 'beginner'
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

cursor.execute('''
CREATE TABLE IF NOT EXISTS weekly_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_of_week TEXT,
    exercise_name TEXT,
    target_sets INTEGER,
    target_reps TEXT,
    target_weight TEXT,
    exercise_order INTEGER,
    notes TEXT,
    created_date TEXT,
    updated_date TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_background (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT 1,
    age INTEGER,
    gender TEXT,
    height TEXT,
    current_weight TEXT,
    fitness_level TEXT,
    years_training INTEGER,
    primary_goal TEXT,
    secondary_goals TEXT,
    injuries_history TEXT,
    current_limitations TEXT,
    past_weight_loss TEXT,
    past_weight_gain TEXT,
    medical_conditions TEXT,
    training_frequency TEXT,
    available_equipment TEXT,
    time_per_session TEXT,
    preferred_training_style TEXT,
    motivation_factors TEXT,
    biggest_challenges TEXT,
    past_program_experience TEXT,
    nutrition_approach TEXT,
    sleep_quality TEXT,
    stress_level TEXT,
    additional_notes TEXT,
    chat_response_style TEXT DEFAULT 'exercise_by_exercise_breakdown',
    chat_progression_detail TEXT DEFAULT 'include_specific_progression_notes_per_exercise',
    onboarding_completed BOOLEAN DEFAULT FALSE,
    created_date TEXT,
    updated_date TEXT
)
''')

cursor.execute('INSERT OR IGNORE INTO users (id, goal, weekly_split, preferences) VALUES (1, "", "", "")')

# Add missing Grok preference columns if they don't exist
try:
    cursor.execute('ALTER TABLE users ADD COLUMN grok_tone TEXT DEFAULT "motivational"')
except sqlite3.OperationalError:
    pass  # Column already exists

try:
    cursor.execute('ALTER TABLE users ADD COLUMN grok_detail_level TEXT DEFAULT "concise"')
except sqlite3.OperationalError:
    pass

try:
    cursor.execute('ALTER TABLE users ADD COLUMN grok_format TEXT DEFAULT "bullet_points"')
except sqlite3.OperationalError:
    pass

try:
    cursor.execute('ALTER TABLE users ADD COLUMN preferred_units TEXT DEFAULT "lbs"')
except sqlite3.OperationalError:
    pass

try:
    cursor.execute('ALTER TABLE users ADD COLUMN communication_style TEXT DEFAULT "encouraging"')
except sqlite3.OperationalError:
    pass

try:
    cursor.execute('ALTER TABLE users ADD COLUMN technical_level TEXT DEFAULT "beginner"')
except sqlite3.OperationalError:
    pass

# Add chat-specific preference columns
try:
    cursor.execute('ALTER TABLE user_background ADD COLUMN chat_response_style TEXT DEFAULT "exercise_by_exercise_breakdown"')
except sqlite3.OperationalError:
    pass

try:
    cursor.execute('ALTER TABLE user_background ADD COLUMN chat_progression_detail TEXT DEFAULT "include_specific_progression_notes_per_exercise"')
except sqlite3.OperationalError:
    pass

conn.commit()

# Fuzzy match for typo tolerance
def is_similar(text1, text2, threshold=0.8):
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio() > threshold

# Get user profile
def get_user_profile():
    cursor.execute("SELECT goal, weekly_split, preferences FROM users WHERE id = 1")
    result = cursor.fetchone()
    return result if result else ("", "", "")

# Check if user has completed onboarding
def is_onboarding_complete():
    cursor.execute("SELECT onboarding_completed FROM user_background WHERE user_id = 1")
    result = cursor.fetchone()
    return result and result[0]

# Get user background for context
def get_user_background():
    cursor.execute("""
        SELECT age, gender, height, current_weight, fitness_level, years_training, 
               primary_goal, secondary_goals, injuries_history, current_limitations,
               past_weight_loss, past_weight_gain, medical_conditions, training_frequency,
               available_equipment, time_per_session, preferred_training_style,
               motivation_factors, biggest_challenges, past_program_experience,
               nutrition_approach, sleep_quality, stress_level, additional_notes,
               chat_response_style, chat_progression_detail
        FROM user_background WHERE user_id = 1
    """)
    result = cursor.fetchone()
    if result:
        return {
            'age': result[0], 'gender': result[1], 'height': result[2], 
            'current_weight': result[3], 'fitness_level': result[4], 
            'years_training': result[5], 'primary_goal': result[6],
            'secondary_goals': result[7], 'injuries_history': result[8],
            'current_limitations': result[9], 'past_weight_loss': result[10],
            'past_weight_gain': result[11], 'medical_conditions': result[12],
            'training_frequency': result[13], 'available_equipment': result[14],
            'time_per_session': result[15], 'preferred_training_style': result[16],
            'motivation_factors': result[17], 'biggest_challenges': result[18],
            'past_program_experience': result[19], 'nutrition_approach': result[20],
            'sleep_quality': result[21], 'stress_level': result[22],
            'additional_notes': result[23], 'chat_response_style': result[24],
            'chat_progression_detail': result[25]
        }
    return None

# Update specific background field
def update_background_field(field_name, value):
    valid_fields = [
        'age', 'gender', 'height', 'current_weight', 'fitness_level', 
        'years_training', 'primary_goal', 'secondary_goals', 'injuries_history',
        'current_limitations', 'past_weight_loss', 'past_weight_gain', 
        'medical_conditions', 'training_frequency', 'available_equipment',
        'time_per_session', 'preferred_training_style', 'motivation_factors',
        'biggest_challenges', 'past_program_experience', 'nutrition_approach',
        'sleep_quality', 'stress_level', 'additional_notes', 'chat_response_style',
        'chat_progression_detail'
    ]

    if field_name in valid_fields:
        # Check if background record exists
        cursor.execute("SELECT id FROM user_background WHERE user_id = 1")
        if cursor.fetchone():
            cursor.execute(f'UPDATE user_background SET {field_name} = ?, updated_date = ? WHERE user_id = 1', 
                         (value, datetime.date.today().isoformat()))
        else:
            cursor.execute(f'''INSERT INTO user_background (user_id, {field_name}, created_date, updated_date)
                             VALUES (1, ?, ?, ?)''', 
                         (value, datetime.date.today().isoformat(), datetime.date.today().isoformat()))
        conn.commit()
        return f"✅ Updated {field_name.replace('_', ' ')}"
    return f"⚠️ Invalid field: {field_name}"

# Comprehensive onboarding flow
def run_onboarding():
    print("\n🎯 Welcome to your Personal Trainer! Let's build your profile for personalized recommendations.")
    print("This will take about 5 minutes and helps me give you better progression advice.\n")

    questions = [
        ("age", "What's your age?", "e.g., 28"),
        ("gender", "Gender? (male/female/prefer not to say)", ""),
        ("height", "Height?", "e.g., 5'10\" or 178cm"),
        ("current_weight", "Current weight?", "e.g., 180lbs or 82kg"),
        ("fitness_level", "Current fitness level? (beginner/intermediate/advanced)", ""),
        ("years_training", "How many years have you been training?", "e.g., 2"),
        ("primary_goal", "Primary fitness goal?", "e.g., build muscle, lose weight, strength"),
        ("secondary_goals", "Any secondary goals?", "e.g., improve endurance, better posture"),
        ("injuries_history", "Past injuries I should know about?", "e.g., lower back injury 2019, knee surgery"),
        ("current_limitations", "Current physical limitations or pain?", "e.g., tight shoulders, can't squat deep"),
        ("past_weight_loss", "Past weight loss efforts/results?", "e.g., lost 30lbs in 2020 with cardio"),
        ("medical_conditions", "Any medical conditions affecting exercise?", "e.g., diabetes, high blood pressure"),
        ("training_frequency", "How often do you want to train per week?", "e.g., 4-5 times"),
        ("available_equipment", "Available equipment?", "e.g., full gym, home dumbbells, bodyweight only"),
        ("time_per_session", "How long per workout session?", "e.g., 60-90 minutes"),
        ("preferred_training_style", "Preferred training style?", "e.g., heavy compound lifts, high volume, functional"),
        ("biggest_challenges", "Biggest fitness challenges?", "e.g., consistency, motivation, plateau"),
        ("past_program_experience", "Programs you've tried before?", "e.g., Starting Strength, P90X, personal trainer"),
        ("nutrition_approach", "Current nutrition approach?", "e.g., tracking macros, intuitive eating, keto"),
        ("sleep_quality", "Sleep quality? (poor/fair/good/excellent)", ""),
        ("stress_level", "Current stress level? (low/moderate/high)", ""),
        ("additional_notes", "Anything else I should know?", "e.g., motivation tips, specific concerns")
    ]

    # Create initial record
    cursor.execute('''INSERT OR REPLACE INTO user_background 
                     (user_id, created_date, updated_date) VALUES (1, ?, ?)''',
                   (datetime.date.today().isoformat(), datetime.date.today().isoformat()))

    for field, question, example in questions:
        while True:
            if example:
                response = input(f"📝 {question} ({example}): ").strip()
            else:
                response = input(f"📝 {question}: ").strip()

            if response or field in ['secondary_goals', 'injuries_history', 'current_limitations', 
                                   'past_weight_loss', 'medical_conditions', 'additional_notes']:
                if not response:
                    response = "None"
                update_background_field(field, response)
                break
            else:
                print("⚠️ This field is required, please provide an answer.")

    # Mark onboarding as complete
    cursor.execute('UPDATE user_background SET onboarding_completed = TRUE WHERE user_id = 1')
    conn.commit()

    print("\n🎉 Profile complete! Now I can give you much better personalized advice.")
    print("You can update any info later with commands like 'update injuries: new knee pain'")
    print("Let's start by setting up your weekly plan!\n")

# Manage background updates
def manage_background(user_input):
    text = user_input.lower()

    # Show background
    if "show background" in text or "show profile" in text or "my profile" in text:
        background = get_user_background()
        if not background:
            return "No background profile found. Run onboarding first!"

        result = "\n👤 Your Background Profile:\n"
        for key, value in background.items():
            if value and value != "None":
                formatted_key = key.replace('_', ' ').title()
                result += f"• {formatted_key}: {value}\n"
        result += "\nTo update: 'update injuries: new info' or 'update age: 29'"
        return result

    # Update background field
    update_pattern = r'update (\w+):\s*(.+)'
    match = re.search(update_pattern, text)
    if match:
        field_name = match.group(1).lower()
        value = match.group(2).strip()
        return update_background_field(field_name, value)

    # Restart onboarding
    if "restart onboarding" in text or "redo profile" in text:
        run_onboarding()
        return "Onboarding completed!"

    return "⚠️ Try 'show profile', 'update injuries: new info', or 'restart onboarding'"

# Get Grok preferences for personalized responses
def get_grok_preferences():
    cursor.execute("""
        SELECT grok_tone, grok_detail_level, grok_format, preferred_units, communication_style, technical_level 
        FROM users WHERE id = 1
    """)
    result = cursor.fetchone()
    if result:
        return {
            'tone': result[0],
            'detail_level': result[1], 
            'format': result[2],
            'units': result[3],
            'communication_style': result[4],
            'technical_level': result[5]
        }
    return {
        'tone': 'motivational',
        'detail_level': 'concise', 
        'format': 'bullet_points',
        'units': 'lbs',
        'communication_style': 'encouraging',
        'technical_level': 'beginner'
    }

# Update Grok preferences
def update_grok_preferences(preference_type, value):
    valid_preferences = {
        'tone': ['motivational', 'analytical', 'casual', 'professional'],
        'detail_level': ['brief', 'concise', 'detailed', 'comprehensive'],
        'format': ['bullet_points', 'paragraphs', 'numbered_lists', 'conversational'],
        'units': ['lbs', 'kg'],
        'communication_style': ['encouraging', 'direct', 'technical', 'friendly'],
        'technical_level': ['beginner', 'intermediate', 'advanced', 'expert']
    }

    if preference_type in valid_preferences and value in valid_preferences[preference_type]:
        column_map = {
            'tone': 'grok_tone',
            'detail_level': 'grok_detail_level', 
            'format': 'grok_format',
            'units': 'preferred_units',
            'communication_style': 'communication_style',
            'technical_level': 'technical_level'
        }

        cursor.execute(f'UPDATE users SET {column_map[preference_type]} = ? WHERE id = 1', (value,))
        conn.commit()
        return f"✅ Updated {preference_type} to '{value}'"
    else:
        return f"⚠️ Invalid {preference_type}. Options: {', '.join(valid_preferences.get(preference_type, []))}"

# Extract numeric weight for progression calculations
def extract_weight_number(weight_str):
    match = re.search(r'(\d+\.?\d*)', str(weight_str))
    return float(match.group(1)) if match else 0

# Set or update weekly workout plan
def set_weekly_plan(day, exercise_name, sets, reps, weight, order=1, notes=""):
    cursor.execute('''
        INSERT OR REPLACE INTO weekly_plan 
        (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, created_date, updated_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (day.lower(), exercise_name.lower(), sets, reps, weight, order, notes, 
          datetime.date.today().isoformat(), datetime.date.today().isoformat()))
    conn.commit()
    print(f"✅ Added to weekly plan: {day} - {exercise_name} {sets}x{reps}@{weight}")

# Get weekly plan for a specific day
def get_weekly_plan(day=None):
    if day:
        cursor.execute('''
            SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
            FROM weekly_plan 
            WHERE day_of_week = ?
            ORDER BY exercise_order
        ''', (day.lower(),))
    else:
        cursor.execute('''
            SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
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
    return cursor.fetchall()

# Update baseline when actual performance exceeds plan
def update_baseline_if_exceeded(exercise_name, actual_sets, actual_reps, actual_weight):
    # Get current baseline for this exercise from weekly plan
    cursor.execute('''
        SELECT target_sets, target_reps, target_weight, day_of_week, exercise_order, notes
        FROM weekly_plan 
        WHERE exercise_name = ?
    ''', (exercise_name.lower(),))

    baseline = cursor.fetchone()
    if not baseline:
        return False

    target_sets, target_reps, target_weight, day, order, notes = baseline

    # Extract numeric values for comparison
    actual_weight_num = extract_weight_number(actual_weight)
    target_weight_num = extract_weight_number(target_weight)

    actual_reps_num = int(actual_reps.split('-')[0]) if '-' in str(actual_reps) else int(actual_reps)
    target_reps_num = int(target_reps.split('-')[0]) if '-' in str(target_reps) else int(target_reps)

    # Check if actual performance exceeds baseline
    exceeded = False
    if actual_weight_num > target_weight_num:
        exceeded = True
    elif actual_weight_num == target_weight_num and actual_sets >= target_sets and actual_reps_num >= target_reps_num:
        exceeded = True

    if exceeded:
        # Update the baseline in weekly plan
        cursor.execute('''
            UPDATE weekly_plan 
            SET target_sets = ?, target_reps = ?, target_weight = ?, updated_date = ?
            WHERE exercise_name = ?
        ''', (actual_sets, actual_reps, actual_weight, datetime.date.today().isoformat(), exercise_name.lower()))
        conn.commit()
        print(f"🔥 BASELINE UPDATED: {exercise_name} baseline updated to {actual_sets}x{actual_reps}@{actual_weight}")
        return True

    return False

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

    # Check for bulk upload or weekly plan commands first (before general workout logging)
    if any(x in text for x in ["bulk upload", "upload plan", "full plan"]) or (("monday:" in text or "tuesday:" in text or "wednesday:" in text or "thursday:" in text or "friday:" in text or "saturday:" in text or "sunday:" in text) and "," in text):
        return "weekly_plan"
    if any(x in text for x in ["weekly split", "my split", "weekly plan", "set plan", "show plan", "set monday", "set tuesday", "set wednesday", "set thursday", "set friday", "set saturday", "set sunday"]) or is_similar(text, "show my split", 0.8):
        return "weekly_plan"

    # Check for background/profile management
    if any(x in text for x in ["show profile", "show background", "my profile", "update injuries", "update age", "update weight", "restart onboarding", "redo profile"]) or text.startswith("update "):
        return "background"

    # Check for preference management
    if any(x in text for x in ["grok preference", "response style", "communication style", "set tone", "set format", "show preferences", "update preferences"]):
        return "preferences"

    # Then check for regular workout logging
    if any(x in text for x in ["did", "sets", "reps", "lbs", "kg", "press", "squat", "kettlebell"]) and re.search(r'\d+', text) and not any(day in text for day in ["monday:", "tuesday:", "wednesday:", "thursday:", "friday:", "saturday:", "sunday:"]):
        return "log"
    if any(x in text for x in ["ready to log", "here is my log", "full log"]):
        return "log-prep"
    if any(x in text for x in ["set my goal", "what's my goal", "show my goal"]):
        return "profile"
    if any(x in text for x in ["why", "don't want", "dont want", "replace", "instead", "swap", "another workout"]) and conversation_history:
        return "follow-up"
    if any(x in text for x in ["progression", "suggest", "tips", "next"]) and not any(x in text for x in ["replace", "another workout"]):
        return "progression"
    if any(x in text for x in ["show", "history", "what did i do", "logs"]) and not is_similar(text, "show my split", 0.8):
        return "query"
    return "chat"

# Enhanced regex parser for workouts
def call_grok_parse(text, date_logged):
    """Parse workout text using Grok API"""
    if not text or not text.strip():
        return None

    # Get user preferences for context - Flask-safe version
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT grok_tone, grok_detail_level, grok_format, preferred_units, communication_style, technical_level 
        FROM users WHERE id = 1
    """)
    result = cursor.fetchone()
    if result:
        preferences = {
            'tone': result[0],
            'detail_level': result[1], 
            'format': result[2],
            'units': result[3],
            'communication_style': result[4],
            'technical_level': result[5]
        }
    else:
        preferences = {
            'tone': 'motivational',
            'detail_level': 'concise', 
            'format': 'bullet_points',
            'units': 'lbs',
            'communication_style': 'encouraging',
            'technical_level': 'beginner'
        }
    conn.close()

    parse_prompt = f"""Parse this workout description into structured data:
"{text}"

Return ONLY a JSON object with these exact keys:
- exercise_name: string (normalized, lowercase)
- sets: integer 
- reps: string (can be range like "8-12" or single number)
- weight: string (include unit like "200lbs" or "bodyweight")
- notes: string (any additional comments about performance, difficulty, etc.)

Examples:
"3x10@200lbs bench press" → {{"exercise_name": "bench press", "sets": 3, "reps": "10", "weight": "200lbs", "notes": ""}}
"did 4x8@225 squats, felt easy" → {{"exercise_name": "squats", "sets": 4, "reps": "8", "weight": "225lbs", "notes": "felt easy"}}
"hanging leg lifts 3x12" → {{"exercise_name": "hanging leg lifts", "sets": 3, "reps": "12", "weight": "bodyweight", "notes": ""}}
"elevated pushups 3x15 bodyweight" → {{"exercise_name": "elevated pushups", "sets": 3, "reps": "15", "weight": "bodyweight", "notes": ""}}

For bodyweight exercises, ALWAYS use "bodyweight" as the weight.
Handle exercises without explicit weight by defaulting to "bodyweight".
Be flexible with natural language but always return valid JSON.
"""

    try:
        client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")
        response = client.chat.completions.create(
            model="grok-4-0709",
            messages=[
                {"role": "system", "content": "You are a workout parser. Return only valid JSON."},
                {"role": "user", "content": parse_prompt}
            ],
            temperature=0.1
        )

        # Try to parse the JSON response
        import json
        result = response.choices[0].message.content.strip()

        # Remove any markdown formatting if present
        if result.startswith('```json'):
            result = result[7:]
        if result.endswith('```'):
            result = result[:-3]

        entry = json.loads(result)
        return entry

    except Exception as e:
        print(f"⚠️ Grok parsing failed: {str(e)}")

        # Fallback to local regex parsing

        # Pattern 1: Standard weight format (3x10@200lbs bench press)
        weight_pattern = r'(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)(lbs|kg)?\s*(.+)'
        weight_match = re.search(weight_pattern, text.lower())

        if weight_match:
            sets, reps, weight, unit, exercise = weight_match.groups()
            if not unit:
                unit = "lbs"

            return {
                "exercise_name": exercise.strip(),
                "sets": int(sets),
                "reps": reps,
                "weight": f"{weight}{unit}",
                "notes": ""
            }

        # Pattern 2: Explicit bodyweight (3x15 bodyweight pushups, 4x12@bodyweight squats)
        bodyweight_explicit_pattern = r'(\d+)x(\d+|\d+-\d+)@?bodyweight\s*(.+)'
        bodyweight_explicit_match = re.search(bodyweight_explicit_pattern, text.lower())

        if bodyweight_explicit_match:
            sets, reps, exercise = bodyweight_explicit_match.groups()
            return {
                "exercise_name": exercise.strip(),
                "sets": int(sets),
                "reps": reps,
                "weight": "bodyweight",
                "notes": ""
            }

        # Pattern 3: Common bodyweight exercises (no weight specified)
        bodyweight_exercises = [
            'pushups', 'push ups', 'pullups', 'pull ups', 'chin ups', 'chinups',
            'dips', 'hanging leg lifts', 'leg lifts', 'sit ups', 'situps',
            'burpees', 'mountain climbers', 'jumping jacks', 'planks',
            'squats', 'lunges', 'calf raises', 'pike pushups', 'elevated pushups',
            'wall sits', 'handstand pushups', 'pistol squats', 'jump squats'
        ]

        # Pattern 4: Standard format but likely bodyweight exercise
        standard_pattern = r'(\d+)x(\d+|\d+-\d+)\s*(.+)'
        standard_match = re.search(standard_pattern, text.lower())

        if standard_match:
            sets, reps, exercise = standard_match.groups()
            exercise_name = exercise.strip()

            # Check if it's a common bodyweight exercise
            is_bodyweight = any(bw_ex in exercise_name for bw_ex in bodyweight_exercises)

            return {
                "exercise_name": exercise_name,
                "sets": int(sets),
                "reps": reps,
                "weight": "bodyweight" if is_bodyweight else "0lbs",
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

            # Check if this exceeds baseline and update if so
            update_baseline_if_exceeded(
                single_entry.get("exercise_name", "Unknown"),
                single_entry.get("sets", 1),
                single_entry.get```python
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

        # Check if this exceeds baseline and update if so
        update_baseline_if_exceeded(
            entry.get("exercise_name", "Unknown"),
            entry.get("sets", 1),
            entry.get("reps", "Unknown"),
            entry.get("weight", "0")
        )

        print(f"✅ Logged: {entry['exercise_name']} - {entry['sets']}x{entry['reps']}@{entry['weight']} on {date_logged}")

    conn.commit()

# Bulk upload weekly plan
def bulk_upload_plan():
    print("\n📋 Bulk Weekly Plan Upload")
    print("Enter your full weekly plan. For each day, format as:")
    print("DAY: exercise1 3x12@180lbs, exercise2 4x8@200lbs, ...")
    print("Example: monday: leg press 3x12@180lbs, squats 4x8@225lbs")
    print("Type 'done' when finished, 'cancel' to abort\n")

    days_data = {}

    while True:
        line = input("Enter day plan: ").strip()
        if line.lower() == 'done':
            break
        if line.lower() == 'cancel':
            return "Upload cancelled."

        # Parse format: "monday: exercise1 3x12@180lbs, exercise2 4x8@200lbs"
        if ':' not in line:
            print("⚠️ Format should be 'day: exercise 3x12@180lbs, exercise2 4x8@200lbs'")
            continue

        day_part, exercises_part = line.split(':', 1)
        day = day_part.strip().lower()

        if day not in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            print("⚠️ Please use valid day names (monday, tuesday, etc.)")
            continue

        # Clear existing plan for this day
        cursor.execute('DELETE FROM weekly_plan WHERE day_of_week = ?', (day,))

        exercises = [ex.strip() for ex in exercises_part.split(',')]
        order = 1

        for exercise_text in exercises:
            # Parse each exercise: "leg press 3x12@180lbs"
            pattern = r'(.+?)\s+(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)(lbs|kg)?'
            match = re.search(pattern, exercise_text.strip())

            if match:
                exercise_name, sets, reps, weight, unit = match.groups()
                if not unit:
                    unit = "lbs"
                weight_with_unit = f"{weight}{unit}"

                set_weekly_plan(day, exercise_name.strip(), int(sets), reps, weight_with_unit, order)
                order += 1
            else:
                print(f"⚠️ Couldn't parse: {exercise_text}")

        print(f"✅ Added {order-1} exercises for {day.title()}")

    conn.commit()
    return f"✅ Bulk upload complete! Use 'show weekly plan' to review."

# Manage weekly workout plan
def manage_weekly_plan(user_input):
    text = user_input.lower()

    # Check for bulk upload request
    if "bulk upload" in text or "upload plan" in text or "full plan" in text:
        return bulk_upload_plan()

    # Check for direct day format like "monday: exercise1 3x12@180lbs, exercise2 4x8@200lbs"
    day_direct_pattern = r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday):\s*(.+)'
    day_match = re.search(day_direct_pattern, text)
    if day_match:
        day, exercises_part = day_match.groups()

        # Clear existing plan for this day
        cursor.execute('DELETE FROM weekly_plan WHERE day_of_week = ?', (day,))

        exercises = [ex.strip() for ex in exercises_part.split(',')]
        order = 1
        added_count = 0

        for exercise_text in exercises:
            # Parse each exercise: "leg press 3x12@180lbs"
            pattern = r'(.+?)\s+(\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)\s*(lbs|kg)?'
            match = re.search(pattern, exercise_text.strip())

            if match:
                exercise_name, sets, reps, weight, unit = match.groups()
                if not unit:
                    unit = "lbs"
                weight_with_unit = f"{weight}{unit}"

                set_weekly_plan(day, exercise_name.strip(), int(sets), reps, weight_with_unit, order)
                order += 1
                added_count += 1
            else:
                print(f"⚠️ Couldn't parse: {exercise_text}")

        conn.commit()
        return f"✅ Added {added_count} exercises to {day.title()}!"

    # Parse plan setting commands like "set monday leg press 3x12@180lbs"
    plan_pattern = r'set (\w+) (.+?) (\d+)x(\d+|\d+-\d+)@(\d+\.?\d*)(lbs|kg)?'
    match = re.search(plan_pattern, text)

    if match:
        day, exercise, sets, reps, weight, unit = match.groups()
        if not unit:
            unit = "lbs"
        weight_with_unit = f"{weight}{unit}"

        # Get current exercise count for this day to set order
        cursor.execute('SELECT COUNT(*) FROM weekly_plan WHERE day_of_week = ?', (day,))
        order = cursor.fetchone()[0] + 1

        set_weekly_plan(day, exercise, int(sets), reps, weight_with_unit, order)
        return f"Added to {day}: {exercise} {sets}x{reps}@{weight_with_unit}"

    # Show weekly plan
    if "show" in text and ("plan" in text or "split" in text):
        plan = get_weekly_plan()
        if not plan:
            return "No weekly plan set. Use format: 'set monday leg press 3x12@180lbs'"

        result = "\n📋 Weekly Workout Plan:\n"
        current_day = ""
        for row in plan:
            day, exercise, sets, reps, weight, order, notes = row
            if day != current_day:
                result += f"\n🔸 {day.title()}:\n"
                current_day = day
            result += f"  {order}. {exercise}: {sets}x{reps}@{weight}\n"
        return result

    # Show specific day
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for day in days:
        if day in text and "show" in text:
            plan = get_weekly_plan(day)
            if not plan:
                return f"No plan set for {day.title()}"

            result = f"\n🔸 {day.title()} Plan:\n"
            for row in plan:
                _, exercise, sets, reps, weight, order, notes = row
                result += f"  {order}. {exercise}: {sets}x{reps}@{weight}\n"
            return result

    return "Use 'set monday leg press 3x12@180lbs' or 'show weekly plan'"

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

# Manage Grok preferences
def manage_preferences(user_input):
    text = user_input.lower()

    # Show current preferences
    if "show preferences" in text or "show my preferences" in text:
        prefs = get_grok_preferences()
        result = "\n🤖 Your Grok Response Preferences:\n"
        result += f"• Tone: {prefs['tone']}\n"
        result += f"• Detail Level: {prefs['detail_level']}\n" 
        result += f"• Format: {prefs['format']}\n"
        result += f"• Units: {prefs['units']}\n"
        result += f"• Communication Style: {prefs['communication_style']}\n"
        result += f"• Technical Level: {prefs['technical_level']}\n"
        result += "\nTo update: 'set tone to casual' or 'set format to paragraphs'"
        return result

    # Update specific preferences
    preference_patterns = {
        'tone': r'set tone to (\w+)',
        'detail_level': r'set detail level to (\w+)',
        'format': r'set format to (\w+)',
        'units': r'set units to (\w+)',
        'communication_style': r'set communication style to (\w+)',
        'technical_level': r'set technical level to (\w+)'
    }

    for pref_type, pattern in preference_patterns.items():
        match = re.search(pattern, text)
        if match:
            value = match.group(1)
            return update_grok_preferences(pref_type, value)

    return "⚠️ Try 'show preferences' or 'set tone to casual'"

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

# Get response from Grok API with context - Flask-safe version
def get_grok_response(prompt, include_context=True):
    client = OpenAI(api_key=os.environ.get("GROK_API_KEY"), base_url="https://api.x.ai/v1")

    if include_context:
        # Use Flask-safe database connections
        conn = sqlite3.connect('workout_logs.db')
        cursor = conn.cursor()

        # Get user profile
        cursor.execute("SELECT goal, weekly_split, preferences FROM users WHERE id = 1")
        profile_result = cursor.fetchone()
        goal, weekly_split, preferences = profile_result if profile_result else ("", "", "")

        # Get Grok preferences
        cursor.execute("""
            SELECT grok_tone, grok_detail_level, grok_format, preferred_units, communication_style, technical_level 
            FROM users WHERE id = 1
        """)
        pref_result = cursor.fetchone()
        if pref_result:
            grok_prefs = {
                'tone': pref_result[0], 'detail_level': pref_result[1], 'format': pref_result[2],
                'units': pref_result[3], 'communication_style': pref_result[4], 'technical_level': pref_result[5]
            }
        else:
            grok_prefs = {'tone': 'motivational', 'detail_level': 'concise', 'format': 'bullet_points',
                         'units': 'lbs', 'communication_style': 'encouraging', 'technical_level': 'beginner'}

        # Get user background
        cursor.execute("""
            SELECT age, gender, height, current_weight, fitness_level, years_training, 
                   primary_goal, secondary_goals, injuries_history, current_limitations,
                   past_weight_loss, past_weight_gain, medical_conditions, training_frequency,
                   available_equipment, time_per_session, preferred_training_style,
                   motivation_factors, biggest_challenges, past_program_experience,
                   nutrition_approach, sleep_quality, stress_level, additional_notes
            FROM user_background WHERE user_id = 1
        """)
        bg_result = cursor.fetchone()
        if bg_result:
            user_background = {
                'age': bg_result[0], 'gender': bg_result[1], 'height': bg_result[2], 
                'current_weight': bg_result[3], 'fitness_level': bg_result[4], 
                'years_training': bg_result[5], 'primary_goal': bg_result[6],
                'secondary_goals': bg_result[7], 'injuries_history': bg_result[8],
                'current_limitations': bg_result[9], 'past_weight_loss': bg_result[10],
                'past_weight_gain': bg_result[11], 'medical_conditions': bg_result[12],
                'training_frequency': bg_result[13], 'available_equipment': bg_result[14],
                'time_per_session': bg_result[15], 'preferred_training_style': bg_result[16],
                'motivation_factors': bg_result[17], 'biggest_challenges': bg_result[18],
                'past_program_experience': bg_result[19], 'nutrition_approach': bg_result[20],
                'sleep_quality': bg_result[21], 'stress_level': bg_result[22],
                'additional_notes': bg_result[23]
            }
        else:
            user_background = None

        # Build personalized context with preferences
        context_info = f"\nUser Profile - Goal: {goal}, Weekly Split: {weekly_split}"
        context_info += f"\n\nResponse Style Preferences:"
        context_info += f"\n- Tone: {grok_prefs['tone']}"
        context_info += f"\n- Detail Level: {grok_prefs['detail_level']}"
        context_info += f"\n- Format: {grok_prefs['format']}"
        context_info += f"\n- Units: {grok_prefs['units']}"
        context_info += f"\n- Communication Style: {grok_prefs['communication_style']}"
        context_info += f"\n- Technical Level: {grok_prefs['technical_level']}"

        # Add comprehensive user background for better context
        if user_background:
            context_info += f"\n\nUser Background & Training History:"
            context_info += f"\n- Age: {user_background['age']}, Gender: {user_background['gender']}"
            context_info += f"\n- Fitness Level: {user_background['fitness_level']} ({user_background['years_training']} years training)"
            context_info += f"\n- Goals: {user_background['primary_goal']}"
            if user_background['secondary_goals'] and user_background['secondary_goals'] != "None":
                context_info += f", {user_background['secondary_goals']}"

            # Critical info for progression planning
            if user_background['injuries_history'] and user_background['injuries_history'] != "None":
                context_info += f"\n- Injury History: {user_background['injuries_history']}"
            if user_background['current_limitations'] and user_background['current_limitations'] != "None":
                context_info += f"\n- Current Limitations: {user_background['current_limitations']}"
            if user_background['past_weight_loss'] and user_background['past_weight_loss'] != "None":
                context_info += f"\n- Weight Loss History: {user_background['past_weight_loss']}"
            if user_background['medical_conditions'] and user_background['medical_conditions'] != "None":
                context_info += f"\n- Medical Conditions: {user_background['medical_conditions']}"

            context_info += f"\n- Training Frequency: {user_background['training_frequency']}"
            context_info += f"\n- Equipment: {user_background['available_equipment']}"
            context_info += f"\n- Session Length: {user_background['time_per_session']}"

            if user_background['biggest_challenges'] and user_background['biggest_challenges'] != "None":
                context_info += f"\n- Challenges: {user_background['biggest_challenges']}"
            if user_background['past_program_experience'] and user_background['past_program_experience'] != "None":
                context_info += f"\n- Past Programs: {user_background['past_program_experience']}"

        # Add complete weekly plan for context
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
        weekly_plan = cursor.fetchall()
        if weekly_plan:
            context_info += "\n\nComplete Weekly Plan:\n"
            current_day = ""
            for row in weekly_plan:
                day, exercise, sets, reps, weight, order = row
                if day != current_day:
                    context_info += f"{day.title()}: "
                    current_day = day
                else:
                    context_info += ", "
                context_info += f"{exercise} {sets}x{reps}@{weight}"
            context_info += "\n"

        # Get recent workout data for context
        cursor.execute("""
            SELECT exercise_name, sets, reps, weight, date_logged, notes
            FROM workouts 
            ORDER BY date_logged DESC 
            LIMIT 20
        """)
        recent_workouts = cursor.fetchall()
        if recent_workouts:
            context_info += "\nRecent Workouts: " + "; ".join([f"{w[0]} {w[1]}x{w[2]}@{w[3]} ({w[4]})" for w in recent_workouts[:5]])

        conn.close()  # Close the connection
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

# Enhanced progression tips using Grok AI
def get_progression_tips(user_input):
    # Get weekly plan for context
    cursor.execute('''
        SELECT DISTINCT exercise_name, target_sets, target_reps, target_weight
        FROM weekly_plan 
        ORDER BY exercise_name
    ''')
    planned_exercises = cursor.fetchall()

    if not planned_exercises:
        print("⚠️ No weekly plan found. Set up your plan first!")
        return

    # Format weekly plan for Grok
    plan_text = ""
    for exercise_name, sets, reps, weight in planned_exercises:
        plan_text += f"• {exercise_name}: {sets}x{reps}@{weight}\n"

    # Create progression prompt for Grok
    progression_prompt = f"""Based on this weekly workout plan, provide specific progression suggestions:

{plan_text}

Please provide progression suggestions in this exact format:
• exercise name: specific suggestion

Keep suggestions practical and progressive (small weight increases, rep adjustments, etc.). Be concise and specific with numbers."""

    print("\n🤖 Getting AI-powered progression suggestions...")

    # Get Grok's response
    response = get_grok_response(progression_prompt, include_context=True)
    print(f"\n{response}")

# Store last 3 interactions for context
conversation_history = []

# Only run console version if this file is executed directly, not when imported
if __name__ == "__main__":
    # Check if user needs onboarding
    if not is_onboarding_complete():
        print("\n🆕 First time setup detected!")
        choice = input("Would you like to complete your profile for personalized recommendations? (y/n): ").lower().strip()
        if choice in ['y', 'yes']:
            run_onboarding()
        else:
            print("You can run onboarding later with 'restart onboarding'\n")

    print("\n💪 Enhanced Personal Trainer: Log workouts, manage weekly plan, view history, or ask for tips. Type 'done' to exit.")
    print("Examples:")
    print("• Log: '3x10@200 bench press'")
    print("• Plan: 'set monday leg press 3x12@180lbs' or 'show weekly plan'")
    print("• Bulk Upload: 'bulk upload plan' (for full 5-day schedule)")
    print("• History: 'show last 7 days'")
    print("• Tips: 'suggest progression for squats'")
    print("• Preferences: 'show preferences' or 'set tone to casual'")
    print("• Profile: 'show profile' or 'update injuries: new info'\n")

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
                # Capture the actual Grok response for follow-up context
                cursor.execute('''
                    SELECT DISTINCT exercise_name, target_sets, target_reps, target_weight
                    FROM weekly_plan 
                    ORDER BY exercise_name
                ''')
                planned_exercises = cursor.fetchall()

                if not planned_exercises:
                    print("⚠️ No weekly plan found. Set up your plan first!")
                    response = "No weekly plan found."
                else:
                    # Format weekly plan for Grok
                    plan_text = ""
                    for exercise_name, sets, reps, weight in planned_exercises:
                        plan_text += f"• {exercise_name}: {sets}x{reps}@{weight}\n"

                    # Create progression prompt for Grok
                    progression_prompt = f"""Based on this weekly workout plan, provide specific progression suggestions:

{plan_text}

Please provide progression suggestions in this exact format:
• exercise name: specific suggestion

Keep suggestions practical and progressive (small weight increases, rep adjustments, etc.). Be concise and specific with numbers."""

                    print("\n🤖 Getting AI-powered progression suggestions...")

                    # Get Grok's response and store it
                    grok_response = get_grok_response(progression_prompt, include_context=True)
                    print(f"\n{grok_response}")
                    response = grok_response  # Store full response for follow-up context

            elif intent == "profile":
                response = update_profile(user_input)
                print(f"🤖 Profile: {response}")

            elif intent == "preferences":
                response = manage_preferences(user_input)
                print(f"🤖 Preferences: {response}")

            elif intent == "background":
                response = manage_background(user_input)
                print(f"🤖 Profile: {response}")

            elif intent == "weekly_plan":
                response = manage_weekly_plan(user_input)
                print(f"🤖 Plan: {response}")

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