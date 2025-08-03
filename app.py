from flask import Flask, request, send_file
from flask_cors import CORS
import requests
import re
import tempfile
import os
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
    
    # Lista per tenere traccia dei file temporanei da pulire
    temp_files = []
    
    try:
        for entry in card_entries:
            name = entry.get("name")
            count = entry.get("count", 1)
            
            print(f"📋 Processando: {name} (x{count})")
            
            image_url = get_card_image_url(name)
            if not image_url:
                print(f"Nessun URL trovato per {name}")
                continue
            
            try:
                print(f"🔗 Scaricando immagine da: {image_url}")
                img_response = requests.get(image_url, timeout=10)
                img_response.raise_for_status()  # Solleva eccezione se status non è 200
                
                # Apri e ridimensiona l'immagine
                img = Image.open(BytesIO(img_response.content)).convert("RGB")
                img = img.resize((540, 750))  # Risoluzione per qualità stampa (180*3, 250*3)
                
                # Salva l'immagine in un file temporaneo
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    img.save(tmp, format="JPEG", quality=95)
                    tmp_path = tmp.name
                    temp_files.append(tmp_path)
                
                # Aggiungi le pagine al PDF
                for i in range(count):
                    pdf.add_page()
                    pdf.image(tmp_path, x=15, y=15, w=180, h=250)
                    print(f"✅ Aggiunta carta {name} ({i+1}/{count})")
                    
            except Exception as e:
                print(f"Errore con {name}: {e}")
                continue
        
        # CORREZIONE PRINCIPALE: Genera il PDF direttamente in BytesIO
        output = BytesIO()
        pdf_content = pdf.output(dest='S')  # Ottieni come stringa
        
        # Se pdf_content è già bytes, usalo direttamente
        if isinstance(pdf_content, bytes):
            output.write(pdf_content)
        else:
            # Se è stringa, convertilo in bytes usando latin1
            output.write(pdf_content.encode('latin1'))
        
        output.seek(0)
        
        print(f"✅ PDF generato con successo. Dimensione: {len(output.getvalue())} bytes")
        
        return send_file(
            output, 
            as_attachment=True, 
            download_name="carte.pdf", 
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Errore generale nella generazione PDF: {e}")
        return {"error": "Errore nella generazione del PDF"}, 500
        
    finally:
        # Pulisci i file temporanei
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except Exception as e:
                print(f"⚠️ Errore nella pulizia del file temporaneo {temp_file}: {e}")

if __name__ == '__main__':
    app.run(debug=True)
