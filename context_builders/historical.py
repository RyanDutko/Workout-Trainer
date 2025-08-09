
import sqlite3
from datetime import datetime

def build_historical_context(prompt):
    """Build context for historical workout queries - ONLY real workout data"""
    print(f"🔍 Building historical context for: '{prompt}'")
    
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    # Check what's actually in the database
    cursor.execute("SELECT COUNT(*) FROM workouts")
    total_workouts = cursor.fetchone()[0]
    print(f"🔍 Total workouts in database: {total_workouts}")
    
    cursor.execute("SELECT exercise_name, date_logged FROM workouts ORDER BY date_logged DESC LIMIT 5")
    recent_workouts_debug = cursor.fetchall()
    print(f"🔍 Recent 5 workouts in DB: {recent_workouts_debug}")

    # Check for specific day requests
    specific_day = None
    for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
        if day in prompt.lower():
            specific_day = day
            print(f"🎯 Detected specific day: '{specific_day}'")
            break

    # Check for general recent workout queries
    general_recent_queries = ['recent logs', 'recent workout', 'most recent', 'last workout', 'latest workout', 'show me my logs']
    is_general_recent = any(phrase in prompt.lower() for phrase in general_recent_queries)

    if is_general_recent and not specific_day:
        print("🎯 Building context for general recent workout query")
        cursor.execute("""
            SELECT exercise_name, sets, reps, weight, date_logged, notes, substitution_reason
            FROM workouts
            ORDER BY date_logged DESC, id ASC
            LIMIT 50
        """)
        recent_logs = cursor.fetchall()

        if recent_logs:
            # Group by date for better organization
            workouts_by_date = {}
            for w in recent_logs:
                date = w[4]
                if date not in workouts_by_date:
                    workouts_by_date[date] = []
                workouts_by_date[date].append(w)

            context_info = "\n" + "=" * 80 + "\n"
            context_info += "=== YOUR ACTUAL RECENT COMPLETED WORKOUTS ===\n"
            context_info += "=" * 80 + "\n"
            
            for date in sorted(workouts_by_date.keys(), reverse=True)[:10]:
                day_name = datetime.strptime(date, '%Y-%m-%d').strftime('%A')
                context_info += f"\n🗓️ {day_name.upper()} {date}:\n"

                for w in workouts_by_date[date]:
                    exercise, sets, reps, weight, _, notes, sub_reason = w
                    context_info += f"   ✓ {exercise}: {sets} sets × {reps} reps @ {weight}"
                    if sub_reason:
                        context_info += f" [SUBSTITUTED FROM: {sub_reason}]"
                    if notes and len(notes) > 0 and not notes.startswith('[SUBSTITUTED'):
                        clean_notes = notes.split('[SUBSTITUTED')[0].strip()
                        if clean_notes:
                            note_preview = clean_notes[:80] + "..." if len(clean_notes) > 80 else clean_notes
                            context_info += f" - {note_preview}"
                    context_info += "\n"
                context_info += "\n"

            context_info += "=" * 80 + "\n"
            context_info += "🚨 CRITICAL INSTRUCTION: These are the user's ACTUAL logged workouts.\n"
            context_info += "DO NOT reference any other workout data. DO NOT make up exercises.\n"
            context_info += "ONLY discuss the exercises listed above with their exact weights and reps.\n"
            context_info += "IGNORE ANY CONVERSATION HISTORY THAT CONTRADICTS THIS DATA.\n"
            context_info += "=" * 80 + "\n"

            print(f"✅ Built historical context with {len(workouts_by_date)} workout days")
            conn.close()
            return context_info
        else:
            print("❌ No recent workouts found in database")
            context_info = "\n" + "=" * 60 + "\n"
            context_info += "❌ NO RECENT WORKOUTS FOUND IN DATABASE\n"
            context_info += "=" * 60 + "\n"
            context_info += "The user asked about recent workouts but no workouts are logged.\n"
            context_info += "DO NOT make up or invent any workouts.\n"
            context_info += "Tell the user truthfully that no recent workouts have been logged.\n"
            context_info += "=" * 60 + "\n"
            conn.close()
            return context_info

    # Handle specific day requests
    if specific_day:
        print(f"🎯 Building context for {specific_day} workouts")
        cursor.execute("""
            SELECT exercise_name, sets, reps, weight, date_logged, notes, substitution_reason
            FROM workouts
            ORDER BY date_logged DESC
            LIMIT 50
        """)
        all_workouts = cursor.fetchall()
        
        specific_day_workouts = []
        for workout in all_workouts:
            exercise, sets, reps, weight, date_str, notes, sub_reason = workout
            try:
                workout_date = datetime.strptime(date_str, '%Y-%m-%d')
                day_name = workout_date.strftime('%A').lower()
                if day_name == specific_day:
                    specific_day_workouts.append((exercise, sets, reps, weight, date_str, notes, sub_reason))
            except Exception as e:
                print(f"❌ Date parsing error for {date_str}: {e}")

        context_info = f"\n🎯 EXACT DATA FOR {specific_day.upper()} WORKOUTS:\n"
        context_info += f"Found {len(specific_day_workouts)} actual {specific_day} workouts in database\n\n"

        if specific_day_workouts:
            most_recent_date = specific_day_workouts[0][4]
            context_info += f"Most recent {specific_day} workout was on {most_recent_date}:\n"
            for workout in specific_day_workouts:
                if workout[4] == most_recent_date:
                    exercise, sets, reps, weight, date_str, notes, sub_reason = workout
                    context_info += f"• {exercise}: {sets}x{reps}@{weight}"
                    if notes:
                        context_info += f" - Notes: {notes}"
                    if sub_reason:
                        context_info += f" - Substituted: {sub_reason}"
                    context_info += "\n"
            context_info += f"\nThis is actual logged data from your {specific_day} workout.\n"
        else:
            context_info += f"No {specific_day} workouts found in your recent logs.\n"

        print(f"✅ Built {specific_day} context with {len(specific_day_workouts)} workouts")
        conn.close()
        return context_info

    conn.close()
    return "\n=== NO HISTORICAL DATA CONTEXT ===\n"
