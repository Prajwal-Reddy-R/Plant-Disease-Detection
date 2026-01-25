from flask import Flask, render_template, request, send_file, redirect, url_for, session, jsonify
import os
from datetime import datetime
import torch
import torchvision.transforms as transforms
from PIL import Image
import torch.nn as nn
import torch.nn.functional as F
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import json

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')

# Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('reports', exist_ok=True)

# Device
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Model class definition - matches the .pth file architecture
class Net(nn.Module):
    def __init__(self, num_classes=38):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 53 * 53, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, num_classes)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = torch.flatten(x, 1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x

# Disease classes
classes = [
    'Apple___Apple_scab', 'Apple___Black_rot', 'Apple___Cedar_apple_rust', 'Apple___healthy',
    'Blueberry___healthy', 'Cherry_(including_sour)___healthy', 'Cherry_(including_sour)___Powdery_mildew',
    'Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot', 'Corn_(maize)___Common_rust_',
    'Corn_(maize)___healthy', 'Corn_(maize)___Northern_Leaf_Blight', 'Grape___Black_rot',
    'Grape___Esca_(Black_Measles)', 'Grape___healthy', 'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)',
    'Orange___Haunglongbing_(Citrus_greening)', 'Peach___Bacterial_spot', 'Peach___healthy',
    'Pepper,_bell___Bacterial_spot', 'Pepper,_bell___healthy', 'Potato___Early_blight',
    'Potato___healthy', 'Potato___Late_blight', 'Raspberry___healthy', 'Soybean___healthy',
    'Squash___Powdery_mildew', 'Strawberry___healthy', 'Strawberry___Leaf_scorch',
    'Tomato___Bacterial_spot', 'Tomato___Early_blight', 'Tomato___healthy', 'Tomato___Late_blight',
    'Tomato___Leaf_Mold', 'Tomato___Septoria_leaf_spot', 'Tomato___Spider_mites Two-spotted_spider_mite',
    'Tomato___Target_Spot'
]

# Load transforms
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225])
])

# Load model
model = Net(num_classes=len(classes))
try:
    model.load_state_dict(torch.load('hybrid_plant_disease_model (1).pth', map_location=device, weights_only=True))
except:
    # Fallback if weights_only=True fails
    model.load_state_dict(torch.load('hybrid_plant_disease_model (1).pth', map_location=device, weights_only=False))

model = model.to(device)
model.eval()

# Load translations
try:
    with open('translations.json', 'r', encoding='utf-8') as f:
        translations = json.load(f)
except:
    translations = {'languages': ['en'], 'en': {}}

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
    return dict(t=get_string, languages=list(translations.get('languages', ['en'])), current_language=lang)

def predict_image(image_path):
    """Predict disease from image"""
    try:
        image = Image.open(image_path).convert('RGB')
        image = transform(image).unsqueeze(0).to(device)
        
        with torch.no_grad():
            output = model(image)
            probabilities = F.softmax(output, dim=1)
            confidence, predicted = torch.max(probabilities, 1)
            confidence = confidence.item()
            predicted_idx = predicted.item()
        
        return classes[predicted_idx], confidence
    except Exception as e:
        print(f"Prediction error: {e}")
        return "Error", 0.0

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        
        if file and file.filename.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            disease, confidence = predict_image(filepath)
            confidence_percent = confidence * 100
            
            return render_template('result.html', 
                                   disease=disease, 
                                   confidence=f"{confidence_percent:.2f}%",
                                   image_path=f'/{filepath}')
    
    return render_template('upload.html')

@app.route('/about')
def about():
    return render_template('features.html')

@app.route('/language/<lang>')
def set_language(lang):
    if lang in translations.get('languages', ['en']):
        session['language'] = lang
    return redirect(request.referrer or url_for('home'))

if __name__ == '__main__':
    print("Starting Plant Disease Detection App...")
    print(f"Visit http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
