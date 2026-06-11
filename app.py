from flask import Flask, request, render_template, jsonify, send_file, session, redirect, url_for, Response
import os
import requests
from predict_image import predict_image, load_model, load_class_names, device, transform
from disease_tracker import DiseaseTracker
from database import DiseaseTrackerDB
from smart_treatment_advisor import SmartTreatmentAdvisor
from report_generator import ReportGenerator
import json
import time

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')

# Load translations
with open('translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

# Add template filters
@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value) if value else None
    except:
        return None

@app.context_processor
def inject_translation():
    lang = session.get('language', 'en')
    def get_string(key):
        return translations.get(lang, {}).get(key, key)
    return dict(t=get_string, languages=translations['languages'], current_language=lang)

@app.route('/language/<lang>')
def set_language(lang):
    if lang in translations['languages']:
        session['language'] = lang
    return redirect(request.referrer or url_for('home'))

# Initialize components with API key
API_KEY = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY') or ''
train_dir = './PlantVillage/color/train'
class_names = load_class_names(train_dir)
model_path = './hybrid_plant_disease_model (1).pth'
model = load_model(model_path, num_classes=len(class_names), device=device)

# Initialize components
disease_tracker = DiseaseTracker(API_KEY)
treatment_advisor = SmartTreatmentAdvisor()
report_generator = ReportGenerator()

@app.route('/set-role', methods=['POST'])
def set_role():
    role = request.form.get('role', 'farmer').lower()
    if role not in ['farmer', 'agronomist']:
        role = 'farmer'
    session['user_role'] = role
    next_url = request.form.get('next') or request.referrer or url_for('home')
    return redirect(next_url)

@app.route('/', methods=['GET', 'POST'])
def home():
    prediction = None
    confidence = None
    error = None
    treatment = None
    report_path = None
    detection_id = None
    uploaded_image_url = None
    
    if request.method == 'POST':
        saved_file_path = None
        # Prefer direct file upload if provided
        try:
            if 'image' in request.files and request.files['image'].filename:
                file = request.files['image']
                upload_dir = os.path.join('static', 'uploads')
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                saved_file_path = os.path.join(upload_dir, file.filename)
                file.save(saved_file_path)
                image_path = saved_file_path
                # Build URL for preview
                uploaded_image_url = '/' + saved_file_path.replace('\\', '/')
            else:
                image_path = request.form.get('image_path')
                if image_path:
                    # Clean up the path
                    image_path = image_path.strip().strip('"').strip("'")
                    image_path = os.path.normpath(image_path)
                    # If user provided a path under static, allow preview
                    try:
                        if image_path.lower().startswith(('static\\', 'static/')):
                            uploaded_image_url = '/' + image_path.replace('\\', '/')
                    except Exception:
                        pass
        except Exception as e:
            error = f"Error saving uploaded image: {str(e)}"
            image_path = None
            
        if image_path:
            # Make prediction
            try:
                pred, conf = predict_image(model, class_names, image_path, device, transform)
                if "Error" in pred or "not found" in pred:
                    error = pred
                else:
                    prediction = pred
                    confidence = conf
                    # Get treatment advice
                    treatment = treatment_advisor.get_treatment(pred)
                    
                    # Record the detection
                    plant_type = pred.split('___')[0]  # Extract plant type from prediction
                    detection_id = disease_tracker.add_detection(
                        plant_type=plant_type,
                        disease=pred,
                        confidence=conf,
                        image_path=image_path
                    )
                    
                    # Generate detailed report
                    report_data = {
                        'prediction': pred,
                        'confidence': conf,
                        'treatment': treatment,
                        'detection_id': detection_id
                    }
                    report_path = report_generator.generate_report(report_data)
            except Exception as e:
                error = f"Error processing image: {str(e)}"
        else:
            if not error:
                error = "Please upload an image or enter an image path."
    
    features = [
        {"icon": "fas fa-leaf", "title": "AI-Powered Disease Detection", "description": "Upload an image to instantly diagnose plant diseases with high accuracy."},
        {"icon": "fas fa-prescription-bottle-alt", "title": "Personalized Treatment Advice", "description": "Receive tailored recommendations for managing identified diseases effectively."},
        {"icon": "fas fa-chart-line", "title": "Disease Tracking & History", "description": "Monitor disease progression over time and review past detection records."},
        {"icon": "fas fa-file-alt", "title": "Comprehensive Reports", "description": "Generate detailed reports for each detection, including analysis and advice."},
        {"icon": "fas fa-chart-pie", "title": "Advanced Analytics Dashboard", "description": "Gain valuable insights into disease patterns, trends, and overall plant health."},
        {"icon": "fas fa-cloud-sun", "title": "Weather Forecasting", "description": "Get real-time weather forecasts to plan your farming activities and protect your crops from adverse weather conditions."}
    ]

    return render_template('home.html', 
                         prediction=prediction, 
                         confidence=confidence, 
                         error=error,
                         treatment=treatment,
                         report_path=report_path,
                         detection_id=detection_id,
                         features=features,
                         class_names=class_names,
                         uploaded_image_url=uploaded_image_url)

@app.route('/disease-tracker', methods=['GET', 'POST'])
def disease_tracker_view():
    plant_id_used = None
    if request.method == 'POST':
        if 'image' not in request.files:
            return "No image found", 400
        
        files = request.files.getlist('image')
        files = [f for f in files if f and f.filename]
        if not files:
            return "No image selected", 400
        
        form_plant_id = request.form.get('plant_id')
        location = request.form.get('location') or "Not specified"
        plant_name = request.form.get('plant_name') or None
        species = request.form.get('species') or None
        
        existing_id = None
        try:
            if form_plant_id:
                existing_id = int(form_plant_id)
        except Exception:
            existing_id = None
        
        upload_dir = os.path.join('static', 'uploads')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        
        last_pred = None
        last_conf = None
        for idx, file in enumerate(files):
            filename = file.filename
            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)
            # Make prediction
            pred, conf = predict_image(model, class_names, filepath, device, transform)
            if "Error" in pred:
                continue
            last_pred, last_conf = pred, conf
            plant_type = pred.split('___')[0]
            if existing_id:
                disease_tracker.add_follow_up_detection(
                    tracked_plant_id=existing_id,
                    disease=pred,
                    confidence=conf,
                    image_path=filepath
                )
                plant_id_used = existing_id
            else:
                # Create on first successful detection
                new_plant_id, _det_id = disease_tracker.add_tracked_plant_with_initial_detection(
                    plant_type=plant_type,
                    disease=pred,
                    confidence=conf,
                    image_path=filepath,
                    location=location,
                    name=plant_name,
                    species=species,
                    photo_path=filepath
                )
                plant_id_used = new_plant_id
                existing_id = new_plant_id

    days = request.args.get('days', default=30, type=int)
    plant_type = request.args.get('plant_type', default=None)
    plant_id = request.args.get('plant_id', default=None, type=int)
    
    # Get all records to extract unique plant types
    all_records = disease_tracker.get_all_records()
    plants = sorted(list(set(record['plant_type'] for record in all_records)))
    
    # Get filtered history (optionally by plant_id)
    history = disease_tracker.get_disease_history(plant_type=plant_type, days=days, plant_id=plant_id)
    
    return render_template('disease_tracker.html',
                         history=history,
                         plants=plants,
                         plant_type=plant_type,
                         days=days,
                         plant_id=plant_id,
                         plant_id_used=plant_id_used)

@app.route('/disease-history')
def disease_history():
    return disease_tracker_view()

@app.route('/batch-upload', methods=['GET', 'POST'])
def batch_upload():
    upload_error = None
    results = []
    created_plant_id = None
    if request.method == 'POST':
        files = request.files.getlist('images')
        files = [f for f in files if f and f.filename]
        if not files:
            upload_error = 'No images selected'
        else:
            target_plant_id = request.form.get('plant_id', type=int)
            plant_name = request.form.get('plant_name') or None
            species = request.form.get('species') or None
            location = request.form.get('location') or 'Not specified'
            upload_dir = os.path.join('static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            for idx, f in enumerate(files):
                path = os.path.join(upload_dir, f.filename)
                f.save(path)
                try:
                    pred, conf = predict_image(model, class_names, path, device, transform)
                    if "Error" in pred:
                        results.append({'file': f.filename, 'error': pred})
                        continue
                    plant_type = pred.split('___')[0]
                    if target_plant_id:
                        disease_tracker.add_follow_up_detection(target_plant_id, pred, conf, path)
                        created_plant_id = target_plant_id
                    else:
                        new_id, _ = disease_tracker.add_tracked_plant_with_initial_detection(plant_type, pred, conf, path, location=location, name=plant_name, species=species, photo_path=path)
                        created_plant_id = new_id
                        target_plant_id = new_id
                    results.append({'file': f.filename, 'prediction': pred, 'confidence': conf})
                except Exception as e:
                    results.append({'file': f.filename, 'error': str(e)})
    return render_template('batch_upload.html', results=results, error=upload_error, created_plant_id=created_plant_id)

@app.route('/plant/<int:plant_id>', methods=['GET', 'POST'])
def plant_dashboard(plant_id):
    try:
        # Ensure database is initialized
        if not hasattr(disease_tracker, 'db'):
            disease_tracker.db = DiseaseTrackerDB()
        disease_tracker.db._create_tables()  # Ensure tables exist
        upload_error = None
        if request.method == 'POST':
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    upload_dir = os.path.join('static', 'uploads')
                    if not os.path.exists(upload_dir):
                        os.makedirs(upload_dir)
                    filepath = os.path.join(upload_dir, file.filename)
                    file.save(filepath)
                    # Normalize path for web URLs
                    web_filepath = filepath.replace('\\', '/')
                    try:
                        pred, conf = predict_image(model, class_names, filepath, device, transform)
                        if "Error" not in pred:
                            # Ensure confidence is a simple float
                            try:
                                conf_value = float(conf)
                            except Exception:
                                conf_value = 0.0
                            disease_tracker.add_follow_up_detection(
                                tracked_plant_id=plant_id,
                                disease=pred,
                                confidence=conf_value,
                                image_path=web_filepath
                            )
                        else:
                            upload_error = pred
                    except Exception as e:
                        upload_error = f"Error processing image: {str(e)}"
                else:
                    upload_error = "No image selected"
            else:
                upload_error = "No image found"
        plant_data = disease_tracker.get_plant_full_history(plant_id)
        if not plant_data:
            return render_template('plant_tracker.html', error='Plant not found', plant=None, detections=[], chart_labels=[], chart_values=[])
        plant = plant_data['plant_info']
        detections = plant_data['detections']
        # Prepare chart data (sorted by date ASC for progression)
        try:
            detections_sorted = sorted(detections, key=lambda d: d['detection_date'])
        except Exception:
            detections_sorted = detections[::-1]
        # Build chart data safely
        chart_labels = []
        chart_values = []
        for d in detections_sorted:
            try:
                chart_labels.append(str(d.get('detection_date') or ''))
            except Exception:
                chart_labels.append('')
            try:
                val = d.get('detected_confidence')
                chart_values.append(float(val) if val is not None else 0.0)
            except Exception:
                chart_values.append(0.0)
        # Ensure public token
        token = disease_tracker.ensure_public_token(plant_id)
        # Build absolute public URL for QR code (avoid double slashes) and try to use LAN IP instead of localhost
        public_url = None
        try:
            if token:
                import socket
                base_url = os.environ.get('PUBLIC_BASE_URL')
                if not base_url:
                    # Derive from request; if localhost/127.0.0.1, replace with LAN IP
                    host = request.host.split(':')[0]
                    try:
                        port = request.host.split(':')[1]
                    except Exception:
                        port = '5000'
                    if host in ('127.0.0.1', 'localhost'):
                        # Find local LAN IP reliably via UDP socket trick
                        try:
                            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            s.connect(('8.8.8.8', 80))
                            lan_ip = s.getsockname()[0]
                            s.close()
                        except Exception:
                            lan_ip = socket.gethostbyname(socket.gethostname())
                        scheme = 'http'
                        base_url = f"{scheme}://{lan_ip}:{port}"
                    else:
                        base_url = request.url_root.rstrip('/')
                public_url = (base_url.rstrip('/') + '/p/' + token)
        except Exception:
            public_url = None
        comments = plant_data.get('comments', [])
        return render_template('plant_tracker.html', plant=plant, detections=detections, chart_labels=chart_labels, chart_values=chart_values, error=upload_error, comments=comments, public_token=token, public_url=public_url, read_only=False, user_role=session.get('user_role','farmer'))
    except Exception as e:
        error_msg = f"Error in plant_dashboard: {str(e)}"
        print(error_msg)
        # Include more specific error message for debugging
        return render_template('plant_tracker.html', 
                             error=f'Error loading plant dashboard: {str(e)}', 
                             plant=None, 
                             detections=[], 
                             chart_labels=[], 
                             chart_values=[], 
                             comments=[], 
                             read_only=False)

@app.route('/plants')
def plants_index():
    try:
        plants = disease_tracker.get_all_tracked_plants()
        return render_template('plants.html', plants=plants)
    except Exception as e:
        print(f"Error in plants_index: {str(e)}")

@app.route('/plant/<int:plant_id>/export.csv')
def export_csv(plant_id):
    plant_data = disease_tracker.get_plant_full_history(plant_id)
    if not plant_data:
        return Response('Plant not found', status=404)
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    p = plant_data['plant_info']
    writer.writerow(['Plant ID', p.get('id')])
    writer.writerow(['Name', p.get('name') or ''])
    writer.writerow(['Species', p.get('species') or ''])
    writer.writerow(['Type', p.get('initial_plant_type')])
    writer.writerow(['Location', p.get('location') or ''])
    writer.writerow([])
    writer.writerow(['Detection ID','Date','Disease','Confidence','Notes','Image Path'])
    for d in plant_data['detections']:
        writer.writerow([d['id'], d['detection_date'], d['detected_disease'], d['detected_confidence'], (d['notes'] or '').replace('\n',' | '), d['image_path'] or ''])
    csv_bytes = output.getvalue()
    return Response(csv_bytes, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=plant_{plant_id}_detections.csv'})

@app.route('/plant/<int:plant_id>/export.xlsx')
def export_xlsx(plant_id):
    # Serve HTML table with Excel-compatible content
    plant_data = disease_tracker.get_plant_full_history(plant_id)
    if not plant_data:
        return Response('Plant not found', status=404)
    p = plant_data['plant_info']
    rows = ''.join([f"<tr><td>{d['id']}</td><td>{d['detection_date']}</td><td>{d['detected_disease']}</td><td>{d['detected_confidence']}</td><td>{(d['notes'] or '').replace('\n',' | ')}</td><td>{d.get('image_path','')}</td></tr>" for d in plant_data['detections']])
    html = f"""
    <html><head><meta charset='utf-8'></head><body>
    <h3>Plant #{p.get('id')} - {p.get('name') or ''}</h3>
    <table border='1'>
      <tr><th>ID</th><th>Date</th><th>Disease</th><th>Confidence</th><th>Notes</th><th>Image Path</th></tr>
      {rows}
    </table>
    </body></html>
    """
    return Response(html, mimetype='application/vnd.ms-excel', headers={'Content-Disposition': f'attachment; filename=plant_{plant_id}_detections.xls'})

@app.route('/p/<token>')
def public_plant(token):
    plant_data = disease_tracker.get_public_plant(token)
    if not plant_data:
        return render_template('plant_tracker.html', error='Public link invalid or plant not found', plant=None, detections=[], chart_labels=[], chart_values=[], comments=[], read_only=True)
    plant = plant_data['plant_info']
    detections = plant_data['detections']
    try:
        detections_sorted = sorted(detections, key=lambda d: d['detection_date'])
    except Exception:
        detections_sorted = detections[::-1]
    # Build chart data safely
    chart_labels = []
    chart_values = []
    for d in detections_sorted:
        try:
            chart_labels.append(str(d.get('detection_date') or ''))
        except Exception:
            chart_labels.append('')
        try:
            val = d.get('detected_confidence')
            chart_values.append(float(val) if val is not None else 0.0)
        except Exception:
            chart_values.append(0.0)
    # Build public URL for QR if possible
    public_url = None
    try:
        token = plant.get('public_token')
        if token:
            import socket
            base_url = os.environ.get('PUBLIC_BASE_URL')
            if not base_url:
                host = request.host.split(':')[0]
                try:
                    port = request.host.split(':')[1]
                except Exception:
                    port = '5000'
                if host in ('127.0.0.1', 'localhost'):
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.connect(('8.8.8.8', 80))
                        lan_ip = s.getsockname()[0]
                        s.close()
                    except Exception:
                        lan_ip = socket.gethostbyname(socket.gethostname())
                    scheme = 'http'
                    base_url = f"{scheme}://{lan_ip}:{port}"
                else:
                    base_url = request.url_root.rstrip('/')
            public_url = (base_url.rstrip('/') + '/p/' + token)
    except Exception:
        public_url = None
    return render_template('plant_tracker.html', plant=plant, detections=detections, chart_labels=chart_labels, chart_values=chart_values, comments=plant_data.get('comments', []), read_only=True, public_token=plant.get('public_token'), public_url=public_url)

@app.route('/plant/<int:plant_id>/comment', methods=['POST'])
def add_comment_route(plant_id):
    role = 'user'
    text = request.form.get('comment', '').strip()
    if text:
        disease_tracker.add_comment(plant_id, role, text)
    return redirect(url_for('plant_dashboard', plant_id=plant_id))

@app.route('/download-report/<detection_id>')
def download_report(detection_id):
    # Generate a new report for the specific detection
    detection_data = disease_tracker.get_disease_progression(detection_id)
    if detection_data:
        report_data = {
            'prediction': detection_data['original_detection'][2],  # disease name
            'confidence': detection_data['original_detection'][3],  # confidence
            'treatment': treatment_advisor.get_treatment(detection_data['original_detection'][2]),
            'progression': detection_data['progression_history']
        }
        report_path = report_generator.generate_report(report_data)
        return send_file(report_path, as_attachment=True)
    return "Report not found", 404

@app.route('/update-progression/<detection_id>', methods=['POST'])
def update_progression(detection_id):
    data = request.json
    disease_tracker.add_progression_update(
        original_detection_id=detection_id,
        disease_status=data.get('status'),
        severity_change=data.get('severity_change'),
        treatment_effectiveness=data.get('treatment_effectiveness'),
        notes=data.get('notes')
    )
    return jsonify({"success": True})

@app.route('/analytics')
def analytics():
    try:
        # Get recent detections from the tracker
        recent_detections = disease_tracker.get_recent_detections(limit=10)
        
        # Calculate statistics
        all_detections = disease_tracker.get_all_records()
        
        # Count diseases and plants
        disease_counts = {}
        plant_counts = {}
        
        for detection in all_detections:
            # Count diseases and format the labels
            disease = detection['disease']
            disease_label = disease.split('___')[-1].replace('_', ' ').title()
            disease_counts[disease_label] = disease_counts.get(disease_label, 0) + 1
            
            # Count plants and format the labels
            plant = detection['plant_type']
            plant_label = plant.replace('_', ' ').title()
            plant_counts[plant_label] = plant_counts.get(plant_label, 0) + 1
        
        # Prepare statistics
        stats = {
            'total_scans': len(all_detections),
            'unique_plants': len(plant_counts),
            'unique_diseases': len(disease_counts),
            'diseases': {
                'labels': list(disease_counts.keys()),
                'data': list(disease_counts.values())
            },
            'plants': {
                'labels': list(plant_counts.keys()),
                'data': list(plant_counts.values())
            }
        }
        
        # Prepare weather data
        weather_data = []
        for detection in all_detections:
            if detection.get('weather_conditions'):
                try:
                    weather = json.loads(detection['weather_conditions'])
                    if weather.get('temperature') is not None:
                        weather_data.append({
                            'x': weather['temperature'],
                            'y': weather['humidity']
                        })
                except:
                    continue
        
        return render_template('analytics_dashboard.html',
                            stats=stats,
                            recent_detections=recent_detections,
                            weather_data=weather_data)
    except Exception as e:
        print(f"Error in analytics route: {str(e)}")
        return render_template('analytics_dashboard.html', 
                             error="Error loading analytics data",
                             stats={'total_scans': 0, 'unique_plants': 0, 'unique_diseases': 0},
                             recent_detections=[],
                             disease_labels=[],
                             disease_data=[],
                             weather_data=[])

@app.route('/treatment/<disease>')
def treatment(disease):
    advice = treatment_advisor.get_treatment(disease)
    return jsonify(advice)

@app.route('/features')
def features():
    return render_template('features.html')

# Legacy-compatible upload endpoint: accepts form-data file field 'img'
@app.route('/upload/', methods=['POST','GET'])
def upload_legacy():
    if request.method == 'POST':
        if 'img' not in request.files:
            return redirect('/')
        file = request.files['img']
        if file.filename == '':
            return redirect('/')
        upload_dir = os.path.join('static', 'uploads')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        filepath = os.path.join(upload_dir, file.filename)
        file.save(filepath)
        try:
            pred, conf = predict_image(model, class_names, filepath, device, transform)
            if "Error" in pred:
                return render_template('home.html', error=pred)
            treatment = treatment_advisor.get_treatment(pred)
            report_data = {
                'prediction': pred,
                'confidence': conf,
                'treatment': treatment,
                'detection_id': None
            }
            report_path = report_generator.generate_report(report_data)
            return render_template('home.html', 
                                   prediction=pred, 
                                   confidence=conf, 
                                   treatment=treatment, 
                                   report_path=report_path,
                                   detection_id=None,
                                   features=[
                                        {"icon": "fas fa-leaf", "title": "AI-Powered Disease Detection", "description": "Upload an image to instantly diagnose plant diseases with high accuracy."},
                                        {"icon": "fas fa-prescription-bottle-alt", "title": "Personalized Treatment Advice", "description": "Receive tailored recommendations for managing identified diseases effectively."},
                                        {"icon": "fas fa-chart-line", "title": "Disease Tracking & History", "description": "Monitor disease progression over time and review past detection records."},
                                        {"icon": "fas fa-file-alt", "title": "Comprehensive Reports", "description": "Generate detailed reports for each detection, including analysis and advice."},
                                        {"icon": "fas fa-chart-pie", "title": "Advanced Analytics Dashboard", "description": "Gain valuable insights into disease patterns, trends, and overall plant health."}
                                   ],
                                   class_names=class_names)
        except Exception as e:
            return render_template('home.html', error=f"Error processing image: {str(e)}")
    else:
        return redirect('/')

@app.route('/supported-diseases')
def supported_diseases():
    return render_template('supported_diseases.html')

# --- Legacy compatibility routes to mirror old project structure ---
@app.route('/analytics-dashboard')
def analytics_dashboard_alias():
    # Reuse existing analytics logic
    return analytics()

@app.route('/dashboard')
def main_dashboard_alias():
    # Old project used /dashboard; map to home
    return home()

@app.route('/api/dashboard-data')
def get_dashboard_data():
    try:
        all_detections = disease_tracker.get_all_records()
        total_scans = len(all_detections)
        # Unique plants and diseases
        plant_ids = set()
        diseases = set()
        for d in all_detections:
            if d.get('tracked_plant_id') is not None:
                plant_ids.add(d['tracked_plant_id'])
            diseases.add(d['disease'])
        return jsonify({
            'success': True,
            'recent_cases': min(5, total_scans),
            'active_alerts': 0,
            'farm_health': {
                'overall_score': 85,
                'status': 'Good',
                'factors': ['Data-driven score not available; placeholder'],
                'recent_cases': total_scans,
                'avg_plant_health': 80
            },
            'totals': {
                'total_scans': total_scans,
                'unique_plants': len(plant_ids),
                'unique_diseases': len(diseases)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- Weather Forecasting and Disease Spread Insights ---
WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY', '773f0308a4d74f1b99c113200252209')


def assess_disease_risk_point(temp_c: float, humidity: float, precip_mm: float, wind_kph: float, chance_of_rain: float | None = None):
    """Compute qualitative disease spread risk and precautions based on weather."""
    risks = []
    precautions = set()

    # Fungal diseases
    if humidity is not None and temp_c is not None:
        if humidity >= 85 and 18 <= temp_c <= 30:
            risks.append('High risk of fungal diseases (powdery mildew, late blight, rust)')
            precautions.update({
                'Avoid overhead irrigation; water early morning at soil level',
                'Improve airflow: prune lower leaves, increase plant spacing',
                'Apply preventive fungicide where appropriate (e.g., copper, mancozeb)'
            })
        elif humidity >= 70 and 15 <= temp_c <= 32:
            risks.append('Moderate risk of fungal diseases')
            precautions.update({
                'Scout leaves (undersides) for spots/lesions 2–3 times this week',
                'Remove heavily infected debris and dispose away from field'
            })

    # Rain-driven spread / bacterial splash
    if (precip_mm or 0) >= 5 or (chance_of_rain or 0) >= 60:
        risks.append('Rain splash favors bacterial and foliar pathogen spread')
        precautions.update({
            'Avoid working in fields when foliage is wet to reduce spread',
            'Use copper-based sprays on susceptible crops before/after rain (label directions)',
            'Stake or trellis plants to keep foliage off the soil'
        })

    # Wind-driven spread
    if wind_kph is not None and wind_kph >= 20:
        risks.append('Wind may increase airborne spore movement and vector activity')
        precautions.update({
            'Delay pruning during windy periods to avoid wounding',
            'Use windbreaks or row covers for young plants if feasible'
        })

    # Hot and dry conditions
    if temp_c is not None and humidity is not None and temp_c >= 30 and humidity <= 40:
        risks.append('Hot and dry: fungal disease pressure lower, monitor for mites/insect vectors')
        precautions.update({
            'Maintain even soil moisture with mulching',
            'Monitor for mites/whiteflies; use IPM controls if thresholds exceeded'
        })

    # Determine overall level
    if any(r.startswith('High') for r in risks):
        level = 'High'
    elif risks:
        level = 'Moderate'
    else:
        level = 'Low'
        precautions.update({
            'Continue regular scouting and sanitation',
            'Rotate crops and avoid overhead irrigation when possible'
        })

    return {
        'level': level,
        'factors': risks,
        'precautions': sorted(list(precautions))
    }


@app.route('/api/weather')
def api_weather():
    try:
        q = request.args.get('q', '').strip()
        days = int(request.args.get('days', '3'))
        if not q:
            return jsonify({'success': False, 'error': 'Missing location parameter q'}), 400
        if not WEATHER_API_KEY:
            return jsonify({'success': False, 'error': 'Weather API key not configured'}), 500
        url = f"https://api.weatherapi.com/v1/forecast.json"
        params = {
            'key': WEATHER_API_KEY,
            'q': q,
            'days': min(max(days, 1), 7),
            'aqi': 'no',
            'alerts': 'no'
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return jsonify({'success': False, 'error': f'Weather API error: {resp.text}'}), 502
        data = resp.json()

        # Build risk assessment for current and each forecast day
        assessments = []
        try:
            current = data.get('current', {})
            temp_c = current.get('temp_c')
            humidity = current.get('humidity')
            wind_kph = current.get('wind_kph')
            precip_mm = current.get('precip_mm')
            assessments.append({
                'type': 'current',
                'risk': assess_disease_risk_point(temp_c, humidity, precip_mm, wind_kph)
            })
        except Exception:
            pass

        for day in data.get('forecast', {}).get('forecastday', []):
            day_info = day.get('day', {})
            temp_c = day_info.get('avgtemp_c')
            humidity = day_info.get('avghumidity')
            wind_kph = day_info.get('maxwind_kph')
            precip_mm = day_info.get('totalprecip_mm')
            chance_of_rain = None
            try:
                hours = day.get('hour') or []
                if hours:
                    chance_of_rain = max([h.get('chance_of_rain') or 0 for h in hours])
            except Exception:
                chance_of_rain = None
            assessments.append({
                'type': 'day',
                'date': day.get('date'),
                'risk': assess_disease_risk_point(temp_c, humidity, precip_mm, wind_kph, chance_of_rain)
            })

        return jsonify({'success': True, 'location': data.get('location'), 'data': data, 'assessments': assessments})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/weather')
def weather_page():
    return render_template('weather.html')


# --- AI Disease Treatment Recommender (Gemini) ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or API_KEY or ''
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
# Gemini request tuning (configurable via environment)
try:
    GEMINI_CONNECT_TIMEOUT = float(os.environ.get('GEMINI_CONNECT_TIMEOUT', '5'))
except Exception:
    GEMINI_CONNECT_TIMEOUT = 5.0
try:
    GEMINI_READ_TIMEOUT = float(os.environ.get('GEMINI_READ_TIMEOUT', '30'))
except Exception:
    GEMINI_READ_TIMEOUT = 30.0
try:
    GEMINI_RETRY_COUNT = int(os.environ.get('GEMINI_RETRY_COUNT', '2'))
except Exception:
    GEMINI_RETRY_COUNT = 2
try:
    GEMINI_RETRY_BACKOFF_MS = int(os.environ.get('GEMINI_RETRY_BACKOFF_MS', '800'))
except Exception:
    GEMINI_RETRY_BACKOFF_MS = 800

def generate_ai_treatments(description: str) -> dict:
    """Call Google Generative Language API (Gemini) to get treatment advice for plant issues.
    Returns a dict with keys: success, text, error (optional).
    """
    try:
        if not description or not description.strip():
            return {'success': False, 'error': 'Please provide a description of the plant problem.'}
        if not GEMINI_API_KEY:
            return {
                'success': True,
                'text': _build_offline_ai_advice(description, 'Gemini API key not configured. Showing offline guidance.'),
                'offline': True,
            }

        system_guidance = (
            "You are an expert agronomist. Based on the user's description of a plant disease or symptom, "
            "provide practical, step-by-step treatment recommendations. Include: immediate actions, cultural "
            "practices, organic/biological controls, and when appropriate, chemical options with active ingredients "
            "(no brands), pre-harvest intervals, and safety precautions. Consider regional variability and advise "
            "the user to verify local regulations and labels. If the description is insufficient, ask 3-5 brief, "
            "targeted follow-up questions. Keep the response concise and actionable."
        )
        user_text = f"Plant issue description:\n{description.strip()}\n\nProvide the best-practice treatment recommendations."

        def call_gemini(api_version: str, model_name: str):
            url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": system_guidance}]},
                    {"role": "user", "parts": [{"text": user_text}]}
                ]
            }
            resp = requests.post(url, json=payload, timeout=(GEMINI_CONNECT_TIMEOUT, GEMINI_READ_TIMEOUT))
            return resp

        # Fallback strategy:
        # 1) v1 with configured model
        # 2) v1 with configured model without '-latest' (if present)
        # 3) v1 with known stable model ids (no '-latest')
        # 4) v1beta with known stable model ids (no '-latest') as last resort
        tried = []
        attempted_keys = set()

        def _ping_gemini_host():
            try:
                # lightweight connectivity check to distinguish DNS/firewall issues
                r = requests.get(
                    'https://generativelanguage.googleapis.com',
                    timeout=(min(GEMINI_CONNECT_TIMEOUT, 3.0), min(GEMINI_READ_TIMEOUT, 5.0))
                )
                return f"host_ok:{r.status_code}"
            except requests.exceptions.RequestException as pe:
                return f"host_unreachable:{type(pe).__name__}:{str(pe)[:160]}"

        def try_call(v, m):
            key = f"{v}|{m}"
            if key in attempted_keys:
                return None
            attempted_keys.add(key)
            last_exc = None
            for attempt in range(max(1, GEMINI_RETRY_COUNT)):
                try:
                    r = call_gemini(v, m)
                    tried.append((v, m, r.status_code, (r.text or '')[:300]))
                    return r
                except requests.exceptions.RequestException as e:
                    last_exc = e
                    ping = _ping_gemini_host()
                    tried.append((v, m, 0, f"RequestException:{type(e).__name__}:{str(e)[:200]}|{ping}"))
                    # backoff before next retry if any
                    if attempt < GEMINI_RETRY_COUNT - 1:
                        try:
                            time.sleep(max(0.0, GEMINI_RETRY_BACKOFF_MS) / 1000.0)
                        except Exception:
                            pass
                        continue
            return None

        # Step 1: v1 with configured model
        resp = try_call('v1', GEMINI_MODEL)
        if resp and resp.status_code == 200:
            pass
        else:
            # Step 2: v1 with non-latest version of configured model
            base_model = GEMINI_MODEL[:-7] if GEMINI_MODEL.endswith('-latest') else GEMINI_MODEL
            if base_model != GEMINI_MODEL:
                r2 = try_call('v1', base_model)
                if r2 and r2.status_code == 200:
                    resp = r2
            # Step 3: v1 with known stable ids
            if not resp or resp.status_code != 200:
                stable_ids = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-001', 'gemini-2.0-flash-lite', 'gemini-2.0-flash-lite-001']
                for mid in stable_ids:
                    if mid == base_model or mid == GEMINI_MODEL:
                        continue
                    r3 = try_call('v1', mid)
                    if r3 and r3.status_code == 200:
                        resp = r3
                        break
            # Step 4: v1beta with known stable ids (no '-latest')
            if not resp or resp.status_code != 200:
                for mid in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-001', 'gemini-2.0-flash-lite', 'gemini-2.0-flash-lite-001']:
                    r4 = try_call('v1beta', mid)
                    if r4 and r4.status_code == 200:
                        resp = r4
                        break

        if not resp or resp.status_code != 200:
            hint = (
                "Gemini models can vary by API version. Try setting environment variable GEMINI_MODEL to a stable id like "
                "'gemini-1.5-flash' and restart the app."
            )
            return {'success': False, 'error': f"Gemini API error: {resp.text if resp else 'No response'}", 'attempts': tried, 'hint': hint}

        data = resp.json()
        # Extract text
        text = ''
        try:
            candidates = data.get('candidates') or []
            for c in candidates:
                parts = ((c.get('content') or {}).get('parts')) or []
                for p in parts:
                    if 'text' in p:
                        text += p['text'] + "\n"
            text = text.strip()
        except Exception:
            text = ''
        if not text:
            text = json.dumps(data)[:1200]
        return {'success': True, 'text': text}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _build_offline_ai_advice(desc: str, err: str = '') -> str:
    desc = (desc or '').strip()
    notice = "Note: Showing offline guidance because the AI service is currently unavailable."
    intro = f"Your description: {desc}\n\n" if desc else ''
    core = (
        "Immediate actions:\n"
        "- Isolate visibly infected plants or leaves. Disinfect tools after cuts.\n"
        "- Remove heavily diseased foliage; dispose away from the field (do not compost if fungal/bacterial).\n\n"
        "Cultural practices:\n"
        "- Improve airflow (prune, space plants), avoid overhead irrigation, irrigate early.\n"
        "- Keep leaves dry; manage weeds and plant debris; rotate with non-host crops 2–3 seasons.\n\n"
        "Organic/biological options:\n"
        "- Neem oil (1% EC) or Bacillus-based bio-fungicides per label; copper soaps for bacterial issues.\n\n"
        "Chemical options (actives only; follow label & local rules):\n"
        "- Fungal leaf spots: Mancozeb, Chlorothalonil, Azoxystrobin, Difenoconazole (rotate FRAC).\n"
        "- Downy/late blights: Copper hydroxide/oxychloride, Cymoxanil+Mancozeb, Mandipropamid.\n"
        "- Bacterial spots: Copper (oxychloride/hydroxide) often with mancozeb.\n"
        "- Typical PHI: 3–14 days (check product label for crop-specific PHI).\n\n"
        "Safety & compliance:\n"
        "- Wear PPE; never exceed label rates; verify permitted actives for your crop/region.\n\n"
        "Follow-up questions (please reply and resubmit):\n"
        "1) Crop/variety and growth stage? 2) Spots: water-soaked/greasy or dry with halos? 3) Recent weather and sprays?\n"
    )
    err_note = f"\n\n(Technical detail: {err[:180]})" if err else ''
    return f"{notice}\n\n{intro}{core}{err_note}"

@app.route('/ai-advisor', methods=['GET', 'POST'])
def ai_advisor_page():
    result = None
    error = None
    # Allow pre-filling the description via GET param 'prefill' (e.g., from detection results)
    description = (request.args.get('prefill') or request.args.get('description') or '').strip()
    if request.method == 'POST':
        description = request.form.get('description', '')
        # If no description, show validation error as before
        if not description.strip():
            error = 'Please describe the crop problem (crop, symptoms, conditions).'
        else:
            out = generate_ai_treatments(description)
            if out.get('success'):
                result = out.get('text')
            else:
                # Graceful offline fallback: show helpful guidance instead of an error banner
                result = _build_offline_ai_advice(description, out.get('error') or '')
                error = None
    return render_template('ai_advisor.html', result=result, error=error, description=description)


@app.route('/api/ai-treatments', methods=['POST'])
def api_ai_treatments():
    try:
        data = request.get_json(silent=True) or {}
        description = data.get('description') or request.form.get('description', '')
        out = generate_ai_treatments(description)
        status = 200 if out.get('success') or out.get('offline') else 400
        return jsonify(out), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    # Bind to all interfaces so QR links using LAN IP work from other devices
    app.run(debug=True, host='0.0.0.0')