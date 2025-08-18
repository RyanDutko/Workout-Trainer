
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

class Database:
    def __init__(self, db_path: str = 'workout_logs.db'):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode = WAL')
        return conn
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table - extensible profile
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_data TEXT NOT NULL DEFAULT '{}',
                ai_preferences TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Training plans - flexible JSON structure
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS training_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                plan_data TEXT NOT NULL DEFAULT '{}',
                philosophy TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Workouts - flexible exercise data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date_logged DATE NOT NULL,
                exercise_data TEXT NOT NULL DEFAULT '{}',
                performance_notes TEXT,
                ai_analysis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # AI conversations - structured interaction history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conversation_type TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                context_data TEXT DEFAULT '{}',
                actions_taken TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Exercise library - AI-enhanced exercise database
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT,
                muscle_groups TEXT DEFAULT '[]',
                equipment TEXT DEFAULT '[]',
                ai_metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create default user if none exists
        cursor.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO users (profile_data, ai_preferences) 
                VALUES ('{}', '{"tone": "motivational", "detail_level": "concise"}')
            ''')
        
        conn.commit()
        conn.close()

class User:
    def __init__(self, db: Database, user_id: int = 1):
        self.db = db
        self.user_id = user_id
    
    def get_profile(self) -> Dict[str, Any]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT profile_data FROM users WHERE id = ?', (self.user_id,))
        result = cursor.fetchone()
        conn.close()
        return json.loads(result[0]) if result else {}
    
    def update_profile(self, profile_data: Dict[str, Any]):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET profile_data = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (json.dumps(profile_data), self.user_id))
        conn.commit()
        conn.close()
    
    def get_ai_preferences(self) -> Dict[str, Any]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT ai_preferences FROM users WHERE id = ?', (self.user_id,))
        result = cursor.fetchone()
        conn.close()
        return json.loads(result[0]) if result else {}

class TrainingPlan:
    def __init__(self, db: Database):
        self.db = db
    
    def get_active_plan(self, user_id: int = 1) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, plan_data, philosophy FROM training_plans 
            WHERE user_id = ? AND is_active = TRUE
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'id': result[0],
                'name': result[1],
                'plan_data': json.loads(result[2]),
                'philosophy': result[3]
            }
        return None
    
    def save_plan(self, user_id: int, name: str, plan_data: Dict[str, Any], philosophy: str = None):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Deactivate current plans
        cursor.execute('UPDATE training_plans SET is_active = FALSE WHERE user_id = ?', (user_id,))
        
        # Insert new plan
        cursor.execute('''
            INSERT INTO training_plans (user_id, name, plan_data, philosophy, is_active)
            VALUES (?, ?, ?, ?, TRUE)
        ''', (user_id, name, json.dumps(plan_data), philosophy))
        
        conn.commit()
        conn.close()

class Workout:
    def __init__(self, db: Database):
        self.db = db
    
    def log_workout(self, user_id: int, date: str, exercises: List[Dict[str, Any]], notes: str = None):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        exercise_data = {
            'exercises': exercises,
            'notes': notes,
            'logged_at': datetime.now().isoformat()
        }
        
        cursor.execute('''
            INSERT INTO workouts (user_id, date_logged, exercise_data, performance_notes)
            VALUES (?, ?, ?, ?)
        ''', (user_id, date, json.dumps(exercise_data), notes))
        
        workout_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return workout_id
    
    def get_recent_workouts(self, user_id: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, date_logged, exercise_data, performance_notes, ai_analysis
            FROM workouts WHERE user_id = ?
            ORDER BY date_logged DESC, created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'date': row[1],
                'exercises': json.loads(row[2]),
                'notes': row[3],
                'ai_analysis': row[4]
            })
        
        conn.close()
        return results
