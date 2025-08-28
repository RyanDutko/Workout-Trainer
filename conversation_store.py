
import sqlite3
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

class ConversationStore:
    def __init__(self, db_path: str = 'workout_logs.db'):
        self.db_path = db_path
        self.init_tables()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute('PRAGMA foreign_keys = ON')
        return conn
    
    def init_tables(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Short-term conversation turns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Pinned facts (long-lived memory)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pinned_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                fact_key TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, fact_key)
            )
        ''')
        
        # Semantic recall (episodic memory)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB
            )
        ''')
        
        # Sticky context (last query state)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                state_key TEXT NOT NULL,
                state_value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, state_key)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def append_turn(self, user_text: str, assistant_text: str, user_id: int = 1):
        """Add a user-assistant turn to short-term memory"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversation_turns (user_id, user_text, assistant_text)
            VALUES (?, ?, ?)
        ''', (user_id, user_text, assistant_text))
        
        # Also store in episodic memory
        cursor.execute('''
            INSERT INTO conversation_episodes (user_id, role, text)
            VALUES (?, 'user', ?)
        ''', (user_id, user_text))
        
        cursor.execute('''
            INSERT INTO conversation_episodes (user_id, role, text) 
            VALUES (?, 'assistant', ?)
        ''', (user_id, assistant_text))
        
        # Keep only last 50 turns to prevent unbounded growth
        cursor.execute('''
            DELETE FROM conversation_turns 
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM conversation_turns 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT 50
            )
        ''', (user_id, user_id))
        
        conn.commit()
        conn.close()
    
    def get_recent_window(self, max_turns: int = 6, user_id: int = 1) -> str:
        """Get recent conversation window as compact text"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_text, assistant_text, created_at
            FROM conversation_turns
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, max_turns))
        
        turns = cursor.fetchall()
        print(f"🔍 Found {len(turns)} turns in conversation_turns table")
        for i, (user_text, assistant_text, created_at) in enumerate(turns):
            user_display = user_text if len(user_text) <= 50 else user_text[:47] + "..."
            assistant_display = assistant_text if len(assistant_text) <= 50 else assistant_text[:47] + "..."
            print(f"🔍 Turn {i+1} ({created_at}): U='{user_display}' A='{assistant_display}'")
        
        conn.close()
        
        if not turns:
            print("🔍 No turns found, returning empty context")
            return ""
        
        # Format as compact recent context
        context = "[RECENT TURNS]\n"
        for user_text, assistant_text, _ in reversed(turns):  # Chronological order
            # Truncate long messages to control token usage
            user_short = user_text[:200] + "..." if len(user_text) > 200 else user_text
            assistant_short = assistant_text[:500] + "..." if len(assistant_text) > 500 else assistant_text
            context += f"- U: {user_short}\n- A: {assistant_short}\n"
        
        return context
    
    def get_pinned_facts(self, user_id: int = 1) -> Dict[str, str]:
        """Get pinned facts as dictionary"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fact_key, fact_value
            FROM pinned_facts
            WHERE user_id = ?
            ORDER BY updated_at DESC
        ''', (user_id,))
        
        facts = dict(cursor.fetchall())
        conn.close()
        return facts
    
    def set_pinned_fact(self, key: str, value: str, user_id: int = 1):
        """Set a pinned fact"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO pinned_facts (user_id, fact_key, fact_value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, key, value))
        
        conn.commit()
        conn.close()
    
    def search_conversation(self, query: str, max_items: int = 3, user_id: int = 1) -> List[Dict[str, Any]]:
        """Search conversation history (keyword-based for now)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Simple keyword search (can be upgraded to embeddings later)
        search_terms = query.lower().split()
        
        cursor.execute('''
            SELECT role, text, timestamp
            FROM conversation_episodes
            WHERE user_id = ? AND (
                {}
            )
            ORDER BY timestamp DESC
            LIMIT ?
        '''.format(' OR '.join(['LOWER(text) LIKE ?' for _ in search_terms])),
        [user_id] + [f'%{term}%' for term in search_terms] + [max_items * 2])
        
        results = []
        for role, text, timestamp in cursor.fetchall():
            # Truncate to control size
            text_short = text[:400] + "..." if len(text) > 400 else text
            results.append({
                'role': role,
                'text': text_short,
                'timestamp': timestamp
            })
        
        conn.close()
        return results[:max_items]
    
    def save_query_context(self, key: str, value: Dict[str, Any], user_id: int = 1):
        """Save sticky context from tool calls"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO conversation_state (user_id, state_key, state_value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, key, json.dumps(value)))
        
        conn.commit()
        conn.close()
    
    def get_last_query_context(self, user_id: int = 1) -> Dict[str, Any]:
        """Get last query context for follow-ups"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT state_key, state_value
            FROM conversation_state
            WHERE user_id = ?
            ORDER BY updated_at DESC
        ''', (user_id,))
        
        context = {}
        for key, value_json in cursor.fetchall():
            try:
                context[key] = json.loads(value_json)
            except json.JSONDecodeError:
                continue
        
        conn.close()
        return context
