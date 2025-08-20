
import sqlite3

def init_normalized_tables():
    conn = sqlite3.connect('workout_logs.db')
    cursor = conn.cursor()
    
    print("NORMALIZE: Creating normalized workout tables...")
    
    # Create workout_sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workout_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            date TEXT NOT NULL,
            notes TEXT,
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sessions_user_date ON workout_sessions(user_id, date)
    ''')
    
    # Create workout_blocks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workout_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            block_type TEXT NOT NULL,
            label TEXT,
            order_index INTEGER NOT NULL DEFAULT 0,
            meta_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(session_id) REFERENCES workout_sessions(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_blocks_session ON workout_blocks(session_id)
    ''')
    
    # Create workout_sets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workout_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id INTEGER NOT NULL,
            set_index INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            FOREIGN KEY(block_id) REFERENCES workout_blocks(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sets_block ON workout_sets(block_id)
    ''')
    
    conn.commit()
    conn.close()
    print("NORMALIZE: Normalized tables created successfully")

if __name__ == "__main__":
    init_normalized_tables()
