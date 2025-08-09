
import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

def migrate_to_postgres():
    # Connect to existing SQLite database
    sqlite_conn = sqlite3.connect('workout_logs.db')
    sqlite_cursor = sqlite_conn.cursor()
    
    # Connect to PostgreSQL using Replit's environment variables
    postgres_conn = psycopg2.connect(os.environ['DATABASE_URL'])
    postgres_cursor = postgres_conn.cursor()
    
    try:
        # Create all tables in PostgreSQL
        create_tables_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            goal TEXT,
            weekly_split TEXT,
            preferences TEXT,
            grok_tone TEXT DEFAULT 'motivational',
            grok_detail_level TEXT DEFAULT 'concise',
            grok_format TEXT DEFAULT 'bullet_points',
            preferred_units TEXT DEFAULT 'lbs',
            communication_style TEXT DEFAULT 'encouraging',
            technical_level TEXT DEFAULT 'beginner'
        );
        
        CREATE TABLE IF NOT EXISTS workouts (
            id SERIAL PRIMARY KEY,
            exercise_name TEXT NOT NULL,
            sets INTEGER,
            reps TEXT,
            weight TEXT,
            notes TEXT,
            date_logged TEXT DEFAULT (CURRENT_DATE::TEXT),
            substitution_reason TEXT,
            performance_context TEXT,
            environmental_factors TEXT,
            difficulty_rating INTEGER,
            gym_location TEXT,
            progression_notes TEXT,
            day_completed BOOLEAN DEFAULT FALSE,
            complex_exercise_data TEXT
        );
        
        CREATE TABLE IF NOT EXISTS weekly_plan (
            id SERIAL PRIMARY KEY,
            day_of_week TEXT NOT NULL,
            exercise_name TEXT NOT NULL,
            target_sets INTEGER,
            target_reps TEXT,
            target_weight TEXT,
            exercise_order INTEGER DEFAULT 1,
            notes TEXT,
            exercise_type TEXT DEFAULT 'working_set',
            progression_rate TEXT DEFAULT 'normal',
            created_by TEXT DEFAULT 'user',
            is_complex BOOLEAN DEFAULT FALSE,
            complex_structure TEXT,
            newly_added BOOLEAN DEFAULT FALSE,
            date_added TEXT
        );
        
        CREATE TABLE IF NOT EXISTS plan_context (
            id SERIAL PRIMARY KEY,
            user_id INTEGER DEFAULT 1,
            plan_philosophy TEXT,
            training_style TEXT,
            weekly_structure TEXT,
            progression_strategy TEXT,
            special_considerations TEXT,
            created_by_ai BOOLEAN DEFAULT FALSE,
            creation_reasoning TEXT,
            created_date TEXT,
            updated_date TEXT
        );
        
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER DEFAULT 1,
            conversation_type TEXT DEFAULT 'general',
            user_message TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            detected_intent TEXT,
            confidence_score REAL DEFAULT 0.0,
            actions_taken TEXT,
            workout_context TEXT,
            exercise_mentioned TEXT,
            form_cues_given TEXT,
            performance_notes TEXT,
            plan_modifications TEXT,
            auto_executed_actions TEXT,
            extracted_workout_data TEXT,
            coaching_context TEXT,
            timestamp TEXT DEFAULT (NOW()::TEXT),
            session_id TEXT,
            conversation_thread_id TEXT,
            parent_conversation_id INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS user_background (
            id SERIAL PRIMARY KEY,
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
        );
        """
        
        postgres_cursor.execute(create_tables_sql)
        
        # Migrate data from each SQLite table
        tables_to_migrate = ['users', 'workouts', 'weekly_plan', 'plan_context', 'conversations', 'user_background']
        
        for table in tables_to_migrate:
            try:
                # Get data from SQLite
                sqlite_cursor.execute(f"SELECT * FROM {table}")
                rows = sqlite_cursor.fetchall()
                
                if rows:
                    # Get column names
                    columns = [description[0] for description in sqlite_cursor.description]
                    columns_str = ', '.join(columns)
                    placeholders = ', '.join(['%s'] * len(columns))
                    
                    # Insert into PostgreSQL
                    insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
                    postgres_cursor.executemany(insert_sql, rows)
                    
                    print(f"Migrated {len(rows)} rows from {table}")
                
            except sqlite3.OperationalError as e:
                print(f"Table {table} doesn't exist in SQLite: {e}")
            except Exception as e:
                print(f"Error migrating {table}: {e}")
        
        postgres_conn.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        postgres_conn.rollback()
    
    finally:
        sqlite_conn.close()
        postgres_conn.close()

if __name__ == "__main__":
    migrate_to_postgres()
