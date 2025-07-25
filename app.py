from flask import Flask, request, send_file
import requests
from fpdf import FPDF
from io import BytesIO
from PIL import Image

app = Flask(__name__)

API_BASE = "https://api.gatcg.com"

def get_card_image_url(card_name):
    response = requests.get(f"{API_BASE}/cards", params={"name": card_name})
    data = response.json()
    if data and data.get("data"):
        return data["data"][0]["image"]
    return None

@app.route('/genera_pdf', methods=['POST'])
def genera_pdf():
    content = request.json
    card_entries = content.get("cards", [])

    pdf = FPDF(unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=10)

    for entry in card_entries:
        name = entry.get("name")
        count = entry.get("count", 1)

        image_url = get_card_image_url(name)
        if not image_url:
            continue

        try:
            img_response = requests.get(image_url)
            img = Image.open(BytesIO(img_response.content)).convert("RGB")
            img = img.resize((180 * 3, 250 * 3))  # Risoluzione per qualità stampa
        except Exception as e:
            print(f"Errore con {name}: {e}")
            continue

        for _ in range(count):
            buffer = BytesIO()
            img.save(buffer, format="JPEG")
            buffer.seek(0)
            pdf.add_page()
            pdf.image(buffer, x=15, y=15, w=180)

    output = BytesIO()
    pdf.output(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="carte.pdf", mimetype='application/pdf')
