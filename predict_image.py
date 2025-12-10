import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms, models
from PIL import Image
import os

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class HybridEfficientNetViT(nn.Module):
    def __init__(self, num_classes=38, use_pretrained=True):
        super().__init__()
        efficientnet_weights = (models.EfficientNet_B0_Weights.IMAGENET1K_V1
                                if use_pretrained else None)
        vit_weights = (models.ViT_B_16_Weights.IMAGENET1K_V1
                       if use_pretrained else None)
        self.efficientnet = models.efficientnet_b0(weights=efficientnet_weights)
        self.efficientnet.classifier = nn.Identity()
        self.vit = models.vit_b_16(weights=vit_weights)
        self.vit.heads = nn.Identity()
        self.fusion_dim = 1280 + 768
        self.attention = nn.MultiheadAttention(embed_dim=self.fusion_dim, num_heads=8, batch_first=True)
        self.classifier = nn.Sequential(
            nn.Linear(self.fusion_dim, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, num_classes)
        )

    def forward(self, x):
        eff_features = self.efficientnet(x)
        vit_features = self.vit(x)
        fused = torch.cat((eff_features, vit_features), dim=1)
        fused = fused.unsqueeze(1)  # [batch, 1, fusion_dim]
        attn_output, _ = self.attention(fused, fused, fused)
        attn_output = attn_output.squeeze(1)
        output = self.classifier(attn_output)
        return output

def predict_image(model, class_names, image_path, device, transform):
    # Clean up the path
    image_path = image_path.replace("'", "").replace('"', "").strip()
    if not os.path.exists(image_path):
        return f"Image not found: {image_path}", 0.0
    try:
        image = Image.open(image_path).convert('RGB')
        image = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            output = model(image)
            probabilities = F.softmax(output, dim=1)
            _, predicted = torch.max(probabilities, 1)
            confidence = probabilities[0][predicted.item()].item()
        return class_names[predicted.item()], confidence
    except Exception as e:
        return f"Error predicting: {e}", 0.0

def load_class_names(train_dir):
    if not os.path.exists(train_dir):
        raise FileNotFoundError("Training directory not found.")
    class_names = sorted(
        [d for d in os.listdir(train_dir) if os.path.isdir(os.path.join(train_dir, d))]
    )
    return class_names

def load_model(model_path, num_classes, device):
    model = HybridEfficientNetViT(num_classes=num_classes, use_pretrained=False)
    # state_dict = torch.load(model_path, map_location=device)
    state_dict = torch.load(model_path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model

transform = transforms.Compose([
    transforms.Resize((224,224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225])
])

if __name__ == '__main__':
    import sys
    
    train_dir = 'C:/Users/darshangouda/MERN/Main Proj/NewOne/PlantVillage/color/train'
    class_names = load_class_names(train_dir)
    model_path = 'C:/Users/darshangouda/MERN/Main Proj/NewOne/hybrid_plant_disease_model (1).pth'
    model = load_model(model_path, num_classes=len(class_names), device=device)

    # Get image path from command line argument
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        print("Please provide an image path.")
        print("Usage: predict_disease.bat <image_path>")
        sys.exit(1)
        
    # Clean up the path
    image_path = image_path.strip().strip('"').strip("'")
    image_path = os.path.normpath(image_path)  # Remove any quotes if present
    pred, conf = predict_image(model, class_names, image_path, device, transform)
    if "Error" in pred:
        print(pred)
    else:
        print(f"Predicted Disease/Class: {pred} (Confidence: {conf:.2f})")

    test_folder = 'P:/FinalYearProject/test_images'
    if os.path.exists(test_folder):
        print("\nBatch Prediction Results:")
        for img_file in os.listdir(test_folder):
            if img_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                img_path = os.path.join(test_folder, img_file)
                pred, conf = predict_image(model, class_names, img_path, device, transform)
                print(f"{img_file}: {pred} (Confidence: {conf:.2f})" if "Error" not in pred else f"{img_file}: {pred}")
