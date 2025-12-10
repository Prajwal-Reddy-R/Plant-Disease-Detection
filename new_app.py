from flask import Flask, render_template, request, send_file, redirect, url_for
import os
from datetime import datetime
import torch
import torchvision.transforms as transforms
from PIL import Image
import torch.nn as nn
import torch.nn.functional as F
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Model class definition
class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 53 * 53, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 38)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = torch.flatten(x, 1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x

# Load the model
model = Net()
model.load_state_dict(torch.load('hybrid_plant_disease_model (1).pth', map_location=torch.device('cpu')))
model.eval()

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
    'Tomato___Target_Spot', 'Tomato___Tomato_mosaic_virus', 'Tomato___Tomato_Yellow_Leaf_Curl_Virus'
]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_prediction(image_path):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    image = Image.open(image_path)
    image = transform(image).unsqueeze(0)
    
    with torch.no_grad():
        outputs = model(image)
        _, predicted = torch.max(outputs, 1)
        
    return classes[predicted]

def generate_report(image_path, prediction, timestamp):
    # Create PDF report
    report_name = f'report_{timestamp}.pdf'
    report_path = os.path.join('static/reports', report_name)
    
    # Ensure reports directory exists
    os.makedirs('static/reports', exist_ok=True)
    
    c = canvas.Canvas(report_path, pagesize=letter)
    c.drawString(100, 750, "Plant Disease Detection Report")
    c.drawString(100, 700, f"Date: {timestamp}")
    c.drawString(100, 650, f"Predicted Disease: {prediction}")
    
    # Add treatment recommendations based on the disease
    treatment = get_treatment_recommendation(prediction)
    y_position = 600
    for line in treatment.split('\n'):
        c.drawString(100, y_position, line)
        y_position -= 20
    
    c.save()
    return report_path

def get_treatment_recommendation(disease):
    treatments = {
        'Apple___Apple_scab': "1. Remove infected leaves and fruit\n2. Apply fungicides in early spring\n3. Maintain good air circulation",
        'Apple___Black_rot': "1. Prune out dead or diseased wood\n2. Remove mummified fruit\n3. Apply fungicides during growing season",
        'Apple___Cedar_apple_rust': "1. Remove nearby cedar trees\n2. Apply preventive fungicides\n3. Plant resistant varieties",
        'Tomato___Late_blight': "1. Remove infected plants\n2. Improve drainage\n3. Apply copper-based fungicides",
        # Add more treatments for other diseases
    }
    return treatments.get(disease, "No specific treatment recommendation available.\nConsult a local agricultural expert.")

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Save uploaded file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"upload_{timestamp}.jpg"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Get prediction
            prediction = get_prediction(filepath)
            
            # Generate report
            report_path = generate_report(filepath, prediction, timestamp)
            
            return render_template('result.html', 
                                filename=filename, 
                                prediction=prediction,
                                report_path=os.path.basename(report_path))
    
    return render_template('index.html')

@app.route('/disease-tracker')
def disease_tracker():
    return render_template('disease_tracker.html')

@app.route('/download-report/<report_name>')
def download_report(report_name):
    report_path = os.path.join('static/reports', report_name)
    return send_file(report_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
