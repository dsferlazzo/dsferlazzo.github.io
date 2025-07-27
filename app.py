from flask import Flask, request, send_file
from flask_cors import CORS
import requests
import re
import tempfile
from fpdf import FPDF
from io import BytesIO
from PIL import Image

app = Flask(__name__)
CORS(app)  # ✅ Abilita CORS su tutte le rotte

API_BASE = "https://api.gatcg.com"

def normalize_card_name(name: str) -> str:
    # 1. togli punteggiatura (tutti i caratteri che non sono lettere, numeri o spazi)
    name = re.sub(r"[^\w\s]", "", name)
    # 2. sostituisci spazi multipli con uno solo
    name = re.sub(r"\s+", " ", name)
    # 3. sostituisci spazi con "-"
    name = name.strip().replace(" ", "-")
    # 4. minuscolo
    name = name.lower()
    return name

def get_card_image_url(card_name):
    try:
        normalized_name = normalize_card_name(card_name)
        response = requests.get(f"{API_BASE}/cards", params={"name": normalized_name})
        if response.status_code != 200:
            print(f"Errore API per {normalized_name}: {response.status_code}")
            return None
        data = response.json()
        if data and data.get("data"):
            card_data = data["data"][0]
            # Prendi il primo elemento "edition" e da lì l'immagine
            editions = card_data.get("editions", [])
            if editions and editions[0].get("image"):
                image_path = editions[0]["image"]
                full_image_url = API_BASE + image_path
                return full_image_url
            print(f"⚠️ Nessuna immagine trovata per {normalized_name}")
            return None
        print(f"⚠️ Nessun risultato per {normalized_name}")
        return None
    except Exception as e:
        print(f"Eccezione in get_card_image_url({normalized_name}): {e}")
        return None


@app.route('/')
def home():
    return "✅ Backend attivo su Render"


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

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(buffer.read())
                tmp.flush()
                pdf.add_page()
                pdf.image(tmp.name, x=15, y=15, w=180, h=250)


    output = BytesIO()
    pdf_data = pdf.output(dest='S').encode('latin1')  # Ottieni PDF come stringa bytes
    output.write(pdf_data)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="carte.pdf", mimetype='application/pdf')

