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

        # Flexible exercise structure that can handle any complexity
        exercise_data = {
            'exercises': exercises,  # Each exercise can have its own structure
            'notes': notes,
            'logged_at': datetime.now().isoformat(),
            'workout_type': self._detect_workout_type(exercises)
        }

        cursor.execute('''
            INSERT INTO workouts (user_id, date_logged, exercise_data, performance_notes)
            VALUES (?, ?, ?, ?)
        ''', (user_id, date, json.dumps(exercise_data), notes))

        workout_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return workout_id

    def _detect_workout_type(self, exercises: List[Dict[str, Any]]) -> str:
        """Detect if this is a simple, complex, or circuit workout"""


class WorkoutTemplateGenerator:
    """Generate workout logging templates based on exercise structure"""

    def __init__(self, db: Database):
        self.db = db

    def generate_logging_template(self, plan_json: List[Dict[str, Any]], date: str, user_id: int = 1) -> Dict[str, Any]:
        """Generate structured template for logging workout"""
        template = {
            "date": date,
            "blocks": []
        }
        
        for plan_block in plan_json:
            block_type = plan_block.get('block_type', 'single')
            block_id = plan_block.get('id', f"block_{len(template['blocks'])}")
            
            if block_type == 'single':
                # Simple exercise - one row
                template["blocks"].append({
                    "block_id": block_id,
                    "type": "simple",
                    "title": plan_block.get('exercise_name', 'Exercise'),
                    "members": [{
                        "name": plan_block.get('exercise_name', 'Exercise'),
                        "input_id": f"{block_id}.1",
                        "planned_reps": plan_block.get('reps', ''),
                        "planned_weight": {"unit": "lb", "value": plan_block.get('weight', '').replace('lbs', '').strip()}
                    }]
                })
            
            elif block_type in ['circuit', 'rounds']:
                # Complex block with rounds
                members = plan_block.get('members', [])
                rounds_count = plan_block.get('rounds', plan_block.get('meta', {}).get('rounds', 1))
                
                block = {
                    "block_id": block_id,
                    "type": "rounds",
                    "title": plan_block.get('label', 'Complex Block'),
                    "rounds": []
                }
                
                for round_idx in range(rounds_count):
                    round_data = {
                        "round_index": round_idx + 1,
                        "members": []
                    }
                    
                    for member in members:
                        weight_str = str(member.get('weight', ''))
                        weight_value = weight_str.replace('lbs', '').replace('lb', '').strip()
                        
                        round_data["members"].append({
                            "name": member.get('exercise', ''),
                            "input_id": f"{block_id}.{round_idx + 1}.{member.get('exercise', '')}",
                            "planned_reps": member.get('reps', ''),
                            "planned_weight": {"unit": "lb", "value": weight_value},
                            "tempo": member.get('tempo', '')
                        })
                    
                    block["rounds"].append(round_data)
                
                template["blocks"].append(block)
        
        return template

    def _generate_custom_fields(self, exercise_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate input fields for completely custom exercise structures"""
        return [
            {'name': 'performance_notes', 'type': 'textarea', 'placeholder': 'Describe how you performed this exercise'},
            {'name': 'intensity', 'type': 'slider', 'min': 1, 'max': 10},
            {'name': 'custom_data', 'type': 'json', 'structure': exercise_data.get('structure', {})}
        ]


        for exercise in exercises:
            if exercise.get('type') in ['rounds', 'circuit', 'complex', 'superset']:
                return 'complex'
        return 'simple'

    def create_exercise_structure(self, exercise_type: str, name: str, **kwargs) -> Dict[str, Any]:
        """Create flexible exercise structures for any workout style"""

        if exercise_type == 'simple':
            return {
                'name': name,
                'type': 'simple',
                'sets': kwargs.get('sets', 3),
                'reps': kwargs.get('reps', '8-12'),
                'weight': kwargs.get('weight', 'bodyweight'),
                'rest': kwargs.get('rest', '60s')
            }

        elif exercise_type == 'rounds':
            return {
                'name': name,
                'type': 'rounds',
                'total_rounds': kwargs.get('rounds', 2),
                'movements': kwargs.get('movements', []),
                'rest_between_rounds': kwargs.get('rest', '2min'),
                'structure': 'rounds'  # e.g., "2 rounds of: 10 slow curls + 15 fast curls + 10 hammer curls"
            }

        elif exercise_type == 'circuit':
            return {
                'name': name,
                'type': 'circuit',
                'movements': kwargs.get('movements', []),
                'circuit_rounds': kwargs.get('rounds', 3),
                'rest_between_circuits': kwargs.get('rest', '90s'),
                'structure': 'circuit'
            }

        elif exercise_type == 'superset':
            return {
                'name': name,
                'type': 'superset',
                'exercises': kwargs.get('exercises', []),
                'sets': kwargs.get('sets', 3),
                'rest_between_supersets': kwargs.get('rest', '90s'),
                'structure': 'superset'
            }

        elif exercise_type == 'tempo':
            return {
                'name': name,
                'type': 'tempo',
                'sets': kwargs.get('sets', 3),
                'reps': kwargs.get('reps', 8),
                'weight': kwargs.get('weight', '135lbs'),
                'tempo': kwargs.get('tempo', '3-1-2-1'),  # eccentric-pause-concentric-pause
                'rest': kwargs.get('rest', '90s')
            }

        else:
            # Completely custom structure
            return {
                'name': name,
                'type': 'custom',
                'structure': kwargs.get('structure', {}),
                'description': kwargs.get('description', '')
            }

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

    def get_weekly_plan(self):
        """Get all weekly plan exercises, including circuit blocks"""
        import json
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Check if we have block_type column for enhanced weekly plan
        try:
            cursor.execute("PRAGMA table_info(weekly_plan)")
            columns = [col[1] for col in cursor.fetchall()]
            has_block_type = 'block_type' in columns
        except:
            has_block_type = False

        if has_block_type:
            cursor.execute('''
                SELECT id, day_of_week, exercise_name, sets, reps, weight, exercise_order, 
                       COALESCE(notes, ""), COALESCE(newly_added, 0), COALESCE(progression_notes, ""),
                       COALESCE(block_type, "single"), COALESCE(meta_json, "{}"), COALESCE(members_json, "[]")
                FROM weekly_plan 
                ORDER BY day_of_week, exercise_order
            ''')

            enhanced_plan = []
            for row in cursor.fetchall():
                # Safely unpack, assuming the structure is consistent or providing defaults
                try:
                    id, day, exercise, sets, reps, weight, order, notes, newly_added, progression_notes, block_type, meta_json, members_json = row
                except ValueError:
                    # Handle cases where the row might not have all expected columns (e.g., older schema)
                    # This is a fallback; the PRAGMA check should ideally prevent this for newer schemas.
                    # If it's an older schema, it will fall through to the 'else' block.
                    enhanced_plan.append(row) # Append as is if structure mismatch
                    continue

                if block_type == "circuit":
                    # Parse circuit data
                    try:
                        meta = json.loads(meta_json) if meta_json else {}
                        members = json.loads(members_json) if members_json else []

                        # Return circuit block info
                        enhanced_plan.append({
                            'id': id,
                            'day_of_week': day,
                            'exercise_name': exercise,
                            'sets': sets,
                            'reps': reps,
                            'weight': weight,
                            'exercise_order': order,
                            'notes': notes,
                            'newly_added': newly_added,
                            'progression_notes': progression_notes,
                            'block_type': block_type,
                            'meta': meta,
                            'members': members
                        })
                    except json.JSONDecodeError:
                        # Handle potential JSON parsing errors for meta_json or members_json
                        # Fallback to standard format or log an error
                        enhanced_plan.append({
                            'id': id,
                            'day_of_week': day,
                            'exercise_name': exercise,
                            'sets': sets,
                            'reps': reps,
                            'weight': weight,
                            'exercise_order': order,
                            'notes': notes,
                            'newly_added': newly_added,
                            'progression_notes': progression_notes,
                            'block_type': block_type, # Keep block_type even if parsing fails
                            'error': 'Failed to parse circuit data'
                        })
                else:
                    # Standard format for non-circuit blocks
                    enhanced_plan.append({
                        'id': id,
                        'day_of_week': day,
                        'exercise_name': exercise,
                        'sets': sets,
                        'reps': reps,
                        'weight': weight,
                        'exercise_order': order,
                        'notes': notes,
                        'newly_added': newly_added,
                        'progression_notes': progression_notes,
                        'block_type': block_type # Include block_type for consistency
                    })

            return enhanced_plan
        else:
            # Legacy format: Fetch data without block_type, meta_json, members_json
            cursor.execute('''
                SELECT id, day_of_week, exercise_name, sets, reps, weight, exercise_order, 
                       COALESCE(notes, ""), COALESCE(newly_added, 0), COALESCE(progression_notes, "")
                FROM weekly_plan 
                ORDER BY day_of_week, exercise_order
            ''')

            # Format legacy data to match the structure of the enhanced plan for consistency
            legacy_plan = []
            for row in cursor.fetchall():
                legacy_plan.append({
                    'id': row[0],
                    'day_of_week': row[1],
                    'exercise_name': row[2],
                    'sets': row[3],
                    'reps': row[4],
                    'weight': row[5],
                    'exercise_order': row[6],
                    'notes': row[7],
                    'newly_added': row[8],
                    'progression_notes': row[9],
                    'block_type': "single" # Assume single block for legacy data
                })
            return legacy_plan