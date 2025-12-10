class SmartTreatmentAdvisor:
    def __init__(self):
        # Each disease entry can include:
        # - chemical: list of chemical control guidance (active ingredients)
        # - biological: list of cultural/biological practices
        # - preventive: list of preventative measures
        # - market_products: list of example market-available treatments (active ingredient + example brand)
        self.treatments = {
            "Apple___Apple_scab": {
                "chemical": [
                    "Captan, Myclobutanil, or Difenoconazole based fungicides (rotate FRAC groups)",
                    "Copper-based fungicides for early-season protection"
                ],
                "biological": [
                    "Remove and destroy infected leaves",
                    "Improve air circulation by pruning",
                    "Clean up fallen leaves in autumn"
                ],
                "preventive": [
                    "Plant resistant varieties",
                    "Maintain proper tree spacing",
                    "Avoid overhead irrigation"
                ],
                "market_products": [
                    "Captan 50% WP/80% WDG (e.g., Captan, Captaf)",
                    "Myclobutanil 20% (e.g., Systhane, Eagle)",
                    "Difenoconazole 25% EC (e.g., Score)",
                    "Copper oxychloride 50% WP (e.g., Blitox, Cobox)"
                ]
            },
            "Tomato___Late_blight": {
                "chemical": [
                    "Copper hydroxide/oxychloride",
                    "Chlorothalonil",
                    "Cymoxanil + Mancozeb or Mandipropamid (rotate modes of action)"
                ],
                "biological": [
                    "Remove infected plants and destroy them",
                    "Improve air circulation",
                    "Avoid wet leaves overnight"
                ],
                "preventive": [
                    "Plant resistant varieties",
                    "Use proper spacing",
                    "Water at the base of plants"
                ],
                "market_products": [
                    "Copper hydroxide 77% WP (e.g., Kocide)",
                    "Chlorothalonil 75% WP (e.g., Daconil)",
                    "Cymoxanil 8% + Mancozeb 64% WP (e.g., Curzate M8)",
                    "Mandipropamid 23.4% SC (e.g., Revus)"
                ]
            },
            "Potato___Early_blight": {
                "chemical": [
                    "Mancozeb, Chlorothalonil, or Azoxystrobin (rotate FRAC groups)",
                    "Use protective sprays before conducive weather"
                ],
                "biological": [
                    "Remove infected debris",
                    "Avoid overhead irrigation",
                    "Improve airflow"
                ],
                "preventive": [
                    "Crop rotation (2–3 years)",
                    "Balanced fertilization to avoid stress",
                    "Irrigate early morning"
                ],
                "market_products": [
                    "Mancozeb 75% WP (e.g., Dithane M-45)",
                    "Chlorothalonil 75% WP (e.g., Bravo/Daconil)",
                    "Azoxystrobin 23% SC (e.g., Amistar)"
                ]
            }
        }
    
    def get_treatment(self, disease):
        if disease in self.treatments:
            return self.treatments[disease]
        return {
            "chemical": ["Consult a local agricultural expert for specific chemical treatments"],
            "biological": ["Remove infected parts", "Improve plant spacing for better air circulation"],
            "preventive": ["Practice crop rotation", "Maintain good garden hygiene"],
            "market_products": [
                "Mancozeb 75% WP (multiple brands)",
                "Copper oxychloride 50% WP (multiple brands)",
                "Neem oil 1% EC (biopesticide, multiple brands)"
            ]
        }
