import sqlite3

def build_general_context(prompt, user_background=None):
    """Build general context for non-specific queries"""
    print("🔍 Building general context")

    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()

    context_info = "\n=== GENERAL FITNESS CONTEXT ===\n"

    # Add user background if available
    if user_background:
        context_info += f"User Goal: {user_background.get('primary_goal', 'Not specified')}\n"
        context_info += f"Experience Level: {user_background.get('fitness_level', 'Not specified')}\n"
        if user_background.get('years_training'):
            context_info += f"Training Experience: {user_background['years_training']} years\n"

    # Check if this is a philosophy discussion and add philosophy context
    philosophy_keywords = ['philosophy', 'training philosophy', 'approach', 'training approach']
    if any(keyword in prompt.lower() for keyword in philosophy_keywords):
        try:
            cursor.execute('''
                SELECT plan_philosophy, weekly_structure, progression_strategy, special_considerations
                FROM plan_context
                WHERE user_id = 1
                ORDER BY created_date DESC
                LIMIT 1
            ''')
            philosophy_data = cursor.fetchone()

            if philosophy_data:
                philosophy, weekly_structure, progression_strategy, special_considerations = philosophy_data
                context_info += "\n=== YOUR TRAINING PHILOSOPHY ===\n"
                if philosophy:
                    context_info += f"Core Philosophy: {philosophy}\n"
                if weekly_structure:
                    context_info += f"Weekly Structure: {weekly_structure}\n"
                if progression_strategy:
                    context_info += f"Progression Strategy: {progression_strategy}\n"
                if special_considerations:
                    context_info += f"Special Considerations: {special_considerations}\n"
        except Exception as e:
            print(f"Error fetching philosophy: {e}")

    # Add basic weekly plan overview
    cursor.execute('SELECT COUNT(DISTINCT day_of_week) FROM weekly_plan')
    training_days = cursor.fetchone()[0] or 0
    context_info += f"Current Training Schedule: {training_days} days per week\n"

    # Add recent activity summary
    cursor.execute('SELECT COUNT(*) FROM workouts WHERE date_logged >= date("now", "-7 days")')
    recent_workouts = cursor.fetchone()[0] or 0
    context_info += f"Recent Activity: {recent_workouts} workouts logged this week\n"

    print("✅ Built general context")
    conn.close()
    return context_info