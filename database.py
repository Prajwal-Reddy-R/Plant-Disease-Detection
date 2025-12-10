import sqlite3
import os
from datetime import datetime

class DiseaseTrackerDB:
    def __init__(self):
        self.db_path = 'disease_tracking.db'
        self._create_tables()
    
    def _create_tables(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Base tables
        c.execute('''CREATE TABLE IF NOT EXISTS tracked_plants
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     initial_plant_type TEXT NOT NULL,
                     initial_disease TEXT NOT NULL,
                     initial_confidence REAL NOT NULL,
                     start_date TIMESTAMP NOT NULL,
                     location TEXT,
                     initial_image_path TEXT,
                     current_status TEXT DEFAULT 'Active')''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS disease_detections
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     tracked_plant_id INTEGER NOT NULL,
                     detected_disease TEXT NOT NULL,
                     detected_confidence REAL NOT NULL,
                     detection_date TIMESTAMP NOT NULL,
                     image_path TEXT,
                     notes TEXT,
                     FOREIGN KEY (tracked_plant_id) REFERENCES tracked_plants(id))''')
        
        # Add new columns to tracked_plants if missing
        try:
            c.execute("PRAGMA table_info(tracked_plants)")
            cols = [row[1] for row in c.fetchall()]
            if 'name' not in cols:
                c.execute("ALTER TABLE tracked_plants ADD COLUMN name TEXT")
            if 'species' not in cols:
                c.execute("ALTER TABLE tracked_plants ADD COLUMN species TEXT")
            if 'photo_path' not in cols:
                c.execute("ALTER TABLE tracked_plants ADD COLUMN photo_path TEXT")
            if 'public_token' not in cols:
                c.execute("ALTER TABLE tracked_plants ADD COLUMN public_token TEXT")
        except Exception:
            pass
        
        # Collaboration comments table
        c.execute('''CREATE TABLE IF NOT EXISTS plant_comments
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     plant_id INTEGER NOT NULL,
                     author_role TEXT NOT NULL,
                     comment_text TEXT NOT NULL,
                     created_at TIMESTAMP NOT NULL,
                     FOREIGN KEY (plant_id) REFERENCES tracked_plants(id))''')
        
        conn.commit()
        conn.close()
    
    def add_tracked_plant(self, initial_plant_type, initial_disease, initial_confidence, location, initial_image_path, name=None, species=None, photo_path=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # photo_path defaults to initial_image_path if not provided
        if photo_path is None:
            photo_path = initial_image_path
        c.execute('''INSERT INTO tracked_plants 
                    (initial_plant_type, initial_disease, initial_confidence, start_date, location, initial_image_path, name, species, photo_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (initial_plant_type, initial_disease, initial_confidence, datetime.now(), location, initial_image_path, name, species, photo_path))
        plant_id = c.lastrowid
        conn.commit()
        conn.close()
        return plant_id

    def add_detection_to_plant(self, tracked_plant_id, detected_disease, detected_confidence, image_path=None, notes=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO disease_detections 
                    (tracked_plant_id, detected_disease, detected_confidence, detection_date, image_path, notes)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                    (tracked_plant_id, detected_disease, detected_confidence, datetime.now(), image_path, notes))
        detection_id = c.lastrowid
        conn.commit()
        conn.close()
        return detection_id

    def get_tracked_plants(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM tracked_plants ORDER BY start_date DESC')
        plants = c.fetchall()
        conn.close()
        return plants

    def set_public_token(self, plant_id, token):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('UPDATE tracked_plants SET public_token = ? WHERE id = ?', (token, plant_id))
        conn.commit()
        conn.close()

    def get_plant_by_public_token(self, token):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM tracked_plants WHERE public_token = ?', (token,))
        plant = c.fetchone()
        conn.close()
        return plant

    def add_comment(self, plant_id, author_role, comment_text):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO plant_comments (plant_id, author_role, comment_text, created_at)
                     VALUES (?, ?, ?, ?)''', (plant_id, author_role, comment_text, datetime.now()))
        conn.commit()
        conn.close()

    def get_comments(self, plant_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT id, plant_id, author_role, comment_text, created_at FROM plant_comments WHERE plant_id = ? ORDER BY created_at DESC', (plant_id,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_plant_detections(self, tracked_plant_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM disease_detections WHERE tracked_plant_id = ? ORDER BY detection_date DESC', (tracked_plant_id,))
        detections = c.fetchall()
        conn.close()
        return detections

    def get_tracked_plant_by_id(self, plant_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM tracked_plants WHERE id = ?', (plant_id,))
        plant = c.fetchone()
        conn.close()
        return plant

    def update_plant_status(self, plant_id, new_status):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('UPDATE tracked_plants SET current_status = ? WHERE id = ?', (new_status, plant_id))
        conn.commit()
        conn.close()

    def get_all_detections(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM disease_detections ORDER BY detection_date DESC')
        detections = c.fetchall()
        conn.close()
        return detections

    def get_detection_by_id(self, detection_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM disease_detections WHERE id = ?', (detection_id,))
        det = c.fetchone()
        conn.close()
        return det

    def append_note_to_detection(self, detection_id, note_text):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Read existing notes
        c.execute('SELECT notes FROM disease_detections WHERE id = ?', (detection_id,))
        row = c.fetchone()
        existing = row[0] if row and row[0] is not None else ''
        new_notes = (existing + '\n' if existing else '') + f"{datetime.now().isoformat()} - {note_text}"
        c.execute('UPDATE disease_detections SET notes = ? WHERE id = ?', (new_notes, detection_id))
        conn.commit()
        conn.close()