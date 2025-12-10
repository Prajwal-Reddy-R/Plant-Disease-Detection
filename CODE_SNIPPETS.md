# Important Code Snippets

This document highlights a few key parts of the codebase with short, practical excerpts and pointers to the full implementations.

- App entrypoint: app.py
- Data access: database.py
- Domain logic: disease_tracker.py
- Treatment knowledge base: smart_treatment_advisor.py
- UI templates: templates/

---

## 1) Image prediction flow (home page upload)
File: app.py

```python
# In route: / (home)
if request.method == 'POST':
    # save upload and build preview URL
    upload_dir = os.path.join('static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    saved_file_path = os.path.join(upload_dir, file.filename)
    file.save(saved_file_path)
    uploaded_image_url = '/' + saved_file_path.replace('\\', '/')

    # run model prediction
    pred, conf = predict_image(model, class_names, saved_file_path, device, transform)
    if 'Error' not in pred:
        treatment = treatment_advisor.get_treatment(pred)

        plant_type = pred.split('___')[0]
        detection_id = disease_tracker.add_detection(
            plant_type=plant_type,
            disease=pred,
            confidence=conf,
            image_path=saved_file_path
        )
```

What it does:
- Saves the uploaded image under static/uploads
- Runs the PyTorch model to get disease and confidence
- Looks up treatment guidance
- Records the detection in SQLite via the tracker

---

## 2) Follow‑up detection on a tracked plant
File: app.py

```python
# In route: /plant/<int:plant_id> (POST)
filepath = os.path.join(upload_dir, file.filename)
file.save(filepath)
web_filepath = filepath.replace('\\', '/')

pred, conf = predict_image(model, class_names, filepath, device, transform)
if 'Error' not in pred:
    conf_value = float(conf) if conf is not None else 0.0
    disease_tracker.add_follow_up_detection(
        tracked_plant_id=plant_id,
        disease=pred,
        confidence=conf_value,
        image_path=web_filepath
    )
```

What it does:
- Adds another detection to an existing tracked plant and normalizes image paths for the UI

---

## 3) Gemini (Google Generative Language) treatment advisor
File: app.py

```python
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', API_KEY)
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash-latest')

def generate_ai_treatments(description: str) -> dict:
    # builds system guidance and user prompt
    # robust multi-attempt strategy across API versions/models
    resp = try_call('v1', GEMINI_MODEL) or ...
    if not resp or resp.status_code != 200:
        return { 'success': False, 'error': 'Gemini API error ...', 'attempts': tried }
    data = resp.json()
    # extract text from candidates -> content.parts[].text
    return { 'success': True, 'text': extracted_text }
```

What it does:
- Calls Gemini with retries, backoff, and model fallbacks (v1 first, then alternatives)
- Returns concise treatment text or a structured error

The corresponding page route renders the UI and gracefully falls back to offline advice when the API fails.

```python
@app.route('/ai-advisor', methods=['GET', 'POST'])
def ai_advisor_page():
    if request.method == 'POST':
        r = generate_ai_treatments(description)
        if not r.get('success'):
            result = _build_offline_ai_advice(description, r.get('error'))
        else:
            result = r.get('text')
    return render_template('ai_advisor.html', ...)
```

---

## 4) Disease tracking DB schema (SQLite)
File: database.py

```python
# Table creation (runs on startup)
c.execute('''CREATE TABLE IF NOT EXISTS tracked_plants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    initial_plant_type TEXT NOT NULL,
    initial_disease TEXT NOT NULL,
    initial_confidence REAL NOT NULL,
    start_date TIMESTAMP NOT NULL,
    location TEXT,
    initial_image_path TEXT,
    current_status TEXT DEFAULT 'Active'
)''')

c.execute('''CREATE TABLE IF NOT EXISTS disease_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracked_plant_id INTEGER NOT NULL,
    detected_disease TEXT NOT NULL,
    detected_confidence REAL NOT NULL,
    detection_date TIMESTAMP NOT NULL,
    image_path TEXT,
    notes TEXT,
    FOREIGN KEY (tracked_plant_id) REFERENCES tracked_plants(id)
)''')

# Optional columns added if missing: name, species, photo_path, public_token
```

What it does:
- Defines the two core tables: tracked plants and their detections
- Adds collaboration comments and public sharing token columns as needed

---

## 5) Domain layer: creating plants and detections
File: disease_tracker.py

```python
class DiseaseTracker:
    def add_tracked_plant_with_initial_detection(self, plant_type, disease, confidence, image_path, location, name=None, species=None):
        plant_id = self.db.add_tracked_plant(
            initial_plant_type=plant_type,
            initial_disease=disease,
            initial_confidence=confidence,
            location=location,
            initial_image_path=image_path,
            name=name,
            species=species,
            photo_path=image_path,
        )
        detection_id = self.db.add_detection_to_plant(plant_id, disease, confidence, image_path)
        return plant_id, detection_id

    def add_follow_up_detection(self, tracked_plant_id, disease, confidence, image_path, notes=""):
        return self.db.add_detection_to_plant(tracked_plant_id, disease, confidence, image_path, notes)
```

What it does:
- Encapsulates DB access and provides a clear API for the Flask app

---

## 6) Built‑in treatment knowledge base
File: smart_treatment_advisor.py

```python
class SmartTreatmentAdvisor:
    def __init__(self):
        self.treatments = {
            'Apple___Apple_scab': {
                'chemical': ['Captan', 'Myclobutanil', 'Difenoconazole', 'Copper-based ...'],
                'biological': ['Remove infected leaves', 'Prune for airflow', ...],
                'preventive': ['Resistant varieties', 'Spacing', 'Avoid overhead irrigation'],
            },
            'Tomato___Late_blight': { ... },
            'Potato___Early_blight': { ... }
        }

    def get_treatment(self, disease):
        return self.treatments.get(disease, { 'chemical': [...], 'biological': [...], 'preventive': [...] })
```

What it does:
- Provides immediate, local advice without external API calls

---

## 7) Public sharing and exports
Files: app.py, disease_tracker.py, database.py, templates/plant_tracker.html

```python
# app.py — create or ensure share token, build public URL
token = disease_tracker.ensure_public_token(plant_id)
public_url = base_url.rstrip('/') + '/p/' + token

# app.py — CSV export route
writer.writerow(['Detection ID','Date','Disease','Confidence','Notes','Image Path'])
for d in plant_data['detections']:
    writer.writerow([d['id'], d['detection_date'], d['detected_disease'], d['detected_confidence'], ...])
```

What it does:
- Generates a shareable, read‑only view of a plant
- Exports detections as CSV/Excel‑compatible HTML

---

## 8) Weather endpoint with disease risk assessment
File: app.py

```python
@app.route('/api/weather')
def api_weather():
    url = 'https://api.weatherapi.com/v1/forecast.json'
    params = { 'key': WEATHER_API_KEY, 'q': q, 'days': days, 'aqi': 'no', 'alerts': 'no' }
    resp = requests.get(url, params=params, timeout=10)
    # Assess risk for current and forecast days using temp/humidity/wind/precip
    assessments.append({ 'type': 'current', 'risk': assess_disease_risk_point(temp_c, humidity, precip_mm, wind_kph) })
```

What it does:
- Wraps WeatherAPI to provide basic disease‑risk signals for the UI

---

## 9) Key template: AI Advisor UI
File: templates/ai_advisor.html

```html
<form method="POST">
  <textarea id="description" name="description" placeholder="Describe the problem...">{{ description or '' }}</textarea>
  <button type="submit" class="btn">Get Recommendations</button>
</form>
{% if result %}
  <div id="resultText" class="result">{{ result | replace('**', '') }}</div>
{% endif %}
```

What it does:
- Minimal UI to submit a description and display AI or offline results

---

Refer to the full source files for complete context and error handling. This page is meant as a quick tour of the most relevant bits for understanding and extending the app.