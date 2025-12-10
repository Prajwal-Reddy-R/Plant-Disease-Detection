from datetime import datetime, timedelta
import json
import requests
from database import DiseaseTrackerDB

class DiseaseTracker:
    def __init__(self, api_key):
        self.api_key = api_key
        self.db = DiseaseTrackerDB()
        
    # --- Legacy compatibility layer for app.py ---
    # The app expects older methods. We provide shims that map to the new schema.
    def add_detection(self, plant_type, disease, confidence, image_path, notes=""):
        try:
            # Create a new tracked plant per detection (simplest safe behavior)
            plant_id, detection_id = self.add_tracked_plant_with_initial_detection(
                plant_type=plant_type,
                disease=disease,
                confidence=confidence,
                image_path=image_path,
                location="Not specified"
            )
            return detection_id
        except Exception as e:
            print(f"Error in add_detection: {str(e)}")
            return None
        
    def get_all_records(self):
        """Return a flat list of detections with keys used by analytics/history views."""
        try:
            detections = self.db.get_all_detections()
            # Build plant id -> plant_type map
            plants = self.db.get_tracked_plants()
            plant_map = {p[0]: p[1] for p in plants}  # id -> initial_plant_type
            records = []
            for d in detections:
                # d: (id, tracked_plant_id, detected_disease, detected_confidence, detection_date, image_path, notes)
                rec = {
                    'id': d[0],
                    'tracked_plant_id': d[1],
                    'plant_type': plant_map.get(d[1], 'Unknown'),
                    'disease': d[2],
                    'confidence': d[3],
                    'detection_date': d[4],
                    'image_path': d[5],
                    'notes': d[6],
                    'weather_conditions': None  # Not stored in current schema
                }
                records.append(rec)
            return records
        except Exception as e:
            print(f"Error in get_all_records: {str(e)}")
            return []
        
    def get_disease_history(self, plant_type=None, days=30, plant_id=None):
        """Return list of dicts with key 'detection' as a tuple-like sequence accessed by template.
        Optional filters: plant_type, plant_id, and days window.
        """
        try:
            all_records = self.get_all_records()
            cutoff = datetime.now() - timedelta(days=days)
            history = []
            for r in all_records:
                # Filter by plant_id, plant_type and date
                try:
                    det_dt = datetime.fromisoformat(str(r['detection_date']))
                except Exception:
                    # If parsing fails, include it by default
                    det_dt = cutoff
                if plant_id and r.get('tracked_plant_id') != plant_id:
                    continue
                if plant_type and r['plant_type'] != plant_type:
                    continue
                if det_dt < cutoff:
                    continue
                # Build a tuple compatible with template indices
                # We'll mimic: [id, plant_type, disease, confidence, detection_date, image_path, notes, severity]
                severity = self._determine_severity(r['confidence'])
                detection_tuple = [
                    r['id'],
                    r['plant_type'],
                    r['disease'],
                    r['confidence'],
                    str(r['detection_date']),
                    r['image_path'],
                    r['notes'],
                    severity
                ]
                history.append({'detection': detection_tuple})
            # Sort by date descending
            history.sort(key=lambda x: x['detection'][4], reverse=True)
            return history
        except Exception as e:
            print(f"Error in get_disease_history: {str(e)}")
            return []
        
    def get_disease_progression(self, detection_id):
        """Return original_detection tuple and progression_history list for reports."""
        try:
            det = self.db.get_detection_by_id(detection_id)
            if not det:
                return None
            # det as in DB ordering
            # Build plant_type
            plant = self.db.get_tracked_plant_by_id(det[1])
            plant_type = plant[1] if plant else 'Unknown'
            severity = self._determine_severity(det[3])
            original_detection = [
                det[0],
                plant_type,
                det[2],
                det[3],
                str(det[4]),
                det[5],
                det[6],
                severity
            ]
            # No separate progression table; return empty list for now
            return {
                'original_detection': original_detection,
                'progression_history': []
            }
        except Exception as e:
            print(f"Error in get_disease_progression: {str(e)}")
            return None
        
    def add_progression_update(self, original_detection_id, disease_status=None, severity_change=None, treatment_effectiveness=None, notes=None):
        """Append a textual note to the detection's notes field to record progression."""
        try:
            fragments = []
            if disease_status:
                fragments.append(f"Status: {disease_status}")
            if severity_change:
                fragments.append(f"Severity Change: {severity_change}")
            if treatment_effectiveness:
                fragments.append(f"Treatment Effectiveness: {treatment_effectiveness}")
            if notes:
                fragments.append(f"Notes: {notes}")
            update_text = ' | '.join(fragments) if fragments else 'Progress update'
            self.db.append_note_to_detection(original_detection_id, update_text)
            return True
        except Exception as e:
            print(f"Error in add_progression_update: {str(e)}")
            return False
        
    def _get_weather_data(self):
        """Fetch current weather data using the OpenWeatherMap API"""
        try:
            # Default coordinates for demonstration (can be made configurable)
            lat, lon = 12.9716, 77.5946  # Bangalore coordinates
            
            url = "http://api.openweathermap.org/data/2.5/weather"
            params = {
                "lat": lat,
                "lon": lon,
                "appid": self.api_key,
                "units": "metric"
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            return {
                "temperature": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "conditions": data["weather"][0]["main"],
                "description": data["weather"][0]["description"]
            }
        except Exception as e:
            print(f"Error fetching weather data: {str(e)}")
            return None
    
    def _determine_severity(self, confidence):
        """Determine disease severity level based on confidence score"""
        if confidence >= 0.9:
            return "High"
        elif confidence >= 0.7:
            return "Medium"
        else:
            return "Low"
        
    def add_tracked_plant_with_initial_detection(self, plant_type, disease, confidence, image_path, location="Not specified", name=None, species=None, photo_path=None):
        try:
            # Add the initial plant to tracked_plants table
            plant_id = self.db.add_tracked_plant(plant_type, disease, confidence, location, image_path, name=name, species=species, photo_path=photo_path)
            
            # Add the initial detection to disease_detections table
            detection_id = self.db.add_detection_to_plant(plant_id, disease, confidence, image_path)
            
            return plant_id, detection_id
        except Exception as e:
            print(f"Error adding tracked plant with initial detection: {str(e)}")
            return None, None

    def add_follow_up_detection(self, tracked_plant_id, disease, confidence, image_path, notes=""):
        try:
            detection_id = self.db.add_detection_to_plant(tracked_plant_id, disease, confidence, image_path, notes)
            return detection_id
        except Exception as e:
            print(f"Error adding follow-up detection: {str(e)}")
            return None

    def get_all_tracked_plants(self):
        try:
            plants_data = self.db.get_tracked_plants()
            # Include extended columns if present
            columns = ["id", "initial_plant_type", "initial_disease", "initial_confidence", "start_date", "location", "initial_image_path", "current_status", "name", "species", "photo_path", "public_token"]
            result = []
            for plant in plants_data:
                # Pad if DB row shorter
                row = list(plant) + [None] * (len(columns) - len(plant))
                result.append(dict(zip(columns, row)))
            return result
        except Exception as e:
            print(f"Error getting all tracked plants: {str(e)}")
            return []

    def get_plant_full_history(self, tracked_plant_id):
        try:
            plant_info = self.db.get_tracked_plant_by_id(tracked_plant_id)
            detections = self.db.get_plant_detections(tracked_plant_id)
            comments_rows = self.db.get_comments(tracked_plant_id)
            
            if plant_info:
                plant_columns = ["id", "initial_plant_type", "initial_disease", "initial_confidence", "start_date", "location", "initial_image_path", "current_status", "name", "species", "photo_path", "public_token"]
                detection_columns = ["id", "tracked_plant_id", "detected_disease", "detected_confidence", "detection_date", "image_path", "notes"]
                comment_columns = ["id", "plant_id", "author_role", "comment_text", "created_at"]
                
                # Pad plant_info if shorter
                row = list(plant_info) + [None] * (len(plant_columns) - len(plant_info))
                return {
                    "plant_info": dict(zip(plant_columns, row)),
                    "detections": [dict(zip(detection_columns, det)) for det in detections],
                    "comments": [dict(zip(comment_columns, r)) for r in comments_rows]
                }
            return None
        except Exception as e:
            print(f"Error getting plant full history: {str(e)}")
            return None

    def update_plant_status(self, plant_id, new_status):
        try:
            self.db.update_plant_status(plant_id, new_status)
            return True
        except Exception as e:
            print(f"Error updating plant status: {str(e)}")
            return False

    def ensure_public_token(self, plant_id):
        """Ensure a shareable token exists for the plant and return it."""
        try:
            plant = self.db.get_tracked_plant_by_id(plant_id)
            if not plant:
                return None
            # public_token expected as last column if exists
            public_token = None
            try:
                public_token = plant[11]  # based on extended columns order
            except Exception:
                public_token = None
            if not public_token:
                import secrets
                token = secrets.token_urlsafe(9)
                self.db.set_public_token(plant_id, token)
                return token
            return public_token
        except Exception as e:
            print(f"Error ensuring public token: {str(e)}")
            return None

    def get_public_plant(self, token):
        try:
            plant = self.db.get_plant_by_public_token(token)
            if not plant:
                return None
            return self.get_plant_full_history(plant[0])
        except Exception as e:
            print(f"Error getting public plant: {str(e)}")
            return None

    def add_comment(self, plant_id, author_role, comment_text):
        try:
            self.db.add_comment(plant_id, author_role, comment_text)
            return True
        except Exception as e:
            print(f"Error adding comment: {str(e)}")
            return False

    def get_comments(self, plant_id):
        try:
            rows = self.db.get_comments(plant_id)
            columns = ["id", "plant_id", "author_role", "comment_text", "created_at"]
            return [dict(zip(columns, r)) for r in rows]
        except Exception as e:
            print(f"Error getting comments: {str(e)}")
            return []

    def get_recent_detections(self, limit=10):
        try:
            detections_data = self.db.get_all_detections() # This gets all detections, need to filter by date/limit
            # For now, just return the latest 'limit' detections from all
            columns = ["id", "tracked_plant_id", "detected_disease", "detected_confidence", "detection_date", "image_path", "notes"]
            recent_detections = [dict(zip(columns, det)) for det in detections_data[:limit]]
            return recent_detections
        except Exception as e:
            print(f"Error getting recent detections: {str(e)}")
            return []

    # The original add_detection and get_disease_history are now replaced by new methods
    # Keeping them commented out for reference if needed, but they are not used with the new schema
    # def add_detection(self, plant_type, disease, confidence, image_path, notes=""):
    #     pass

    # def get_disease_history(self, plant_type=None, days=30):
    #     pass