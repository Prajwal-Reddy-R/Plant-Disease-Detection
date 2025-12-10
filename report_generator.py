import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

class ReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.report_dir = "reports"
        if not os.path.exists(self.report_dir):
            os.makedirs(self.report_dir)

    def generate_report(self, data):
        """Generate a detailed PDF report for plant disease detection"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.report_dir}/plant_disease_report_{timestamp}.pdf"
        
        doc = SimpleDocTemplate(filename, pagesize=letter)
        story = []

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER
        )
        story.append(Paragraph("Plant Disease Analysis Report", title_style))
        story.append(Spacer(1, 12))

        # Date and Time
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", self.styles["Normal"]))
        story.append(Spacer(1, 12))

        # Analysis Results
        story.append(Paragraph("Analysis Results", self.styles["Heading2"]))
        story.append(Spacer(1, 12))

        results_data = [
            ["Plant Disease Details", "Value"],
            ["Detected Disease", data['prediction']],
            ["Confidence Score", f"{data['confidence']:.2%}"],
            ["Plant Type", data['prediction'].split('___')[0]],
        ]

        results_table = Table(results_data, colWidths=[3*inch, 3*inch])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.green),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(results_table)
        story.append(Spacer(1, 20))

        # Treatment Recommendations
        if 'treatment' in data:
            story.append(Paragraph("Treatment Recommendations", self.styles["Heading2"]))
            story.append(Spacer(1, 12))

            treatment_data = []
            treatment_data.append(["Category", "Recommendations"])

            for category, recommendations in data['treatment'].items():
                for rec in recommendations:
                    treatment_data.append([category.title(), rec])

            treatment_table = Table(treatment_data, colWidths=[2*inch, 4*inch])
            treatment_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.green),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(treatment_table)

        # Weather Integration Note
        story.append(Spacer(1, 20))
        story.append(Paragraph("Note: This report includes AI-powered analysis using advanced plant disease recognition technology.", self.styles["Italic"]))

        doc.build(story)
        return filename
