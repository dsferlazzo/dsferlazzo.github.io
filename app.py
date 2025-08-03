from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import requests
import re
import tempfile
import os
from fpdf import FPDF
from io import BytesIO
from PIL import Image

app = Flask(__name__)
CORS(app)

API_BASE = "https://api.gatcg.com"

def normalize_card_name(name: str) -> str:
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip().replace(" ", "-")
    name = name.lower()
    return name

def get_card_image_url(card_name):
    try:
        normalized_name = normalize_card_name(card_name)
        print(f"🔍 Cercando: {card_name} → {normalized_name}")
        
        response = requests.get(f"{API_BASE}/cards", params={"name": normalized_name}, timeout=10)
        print(f"📡 API Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Errore API per {normalized_name}: {response.status_code}")
            return None
            
        data = response.json()
        print(f"📊 Dati ricevuti: {bool(data and data.get('data'))}")
        
        if data and data.get("data"):
            card_data = data["data"][0]
            editions = card_data.get("editions", [])
            if editions and editions[0].get("image"):
                image_path = editions[0]["image"]
                full_image_url = API_BASE + image_path
                print(f"🖼️ URL immagine: {full_image_url}")
                return full_image_url
                
        print(f"⚠️ Nessuna immagine trovata per {normalized_name}")
        return None
        
    except Exception as e:
        print(f"❌ Eccezione in get_card_image_url({card_name}): {e}")
        return None

@app.route('/')
def home():
    return "✅ Backend attivo su Render"

@app.route('/test_api')
def test_api():
    """Endpoint per testare l'API esterna"""
    try:
        response = requests.get(f"{API_BASE}/cards", params={"name": "lorraine"}, timeout=10)
        return jsonify({
            "status": response.status_code,
            "data": response.json() if response.status_code == 200 else "Error"
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/genera_pdf', methods=['POST'])
def genera_pdf():
    try:
        print("🚀 Iniziando generazione PDF...")
        
        # Verifica dati di input
        if not request.json:
            return jsonify({"error": "Nessun dato JSON ricevuto"}), 400
            
        content = request.json
        card_entries = content.get("cards", [])
        
        print(f"📋 Carte da processare: {len(card_entries)}")
        for entry in card_entries:
            print(f"  - {entry.get('name')} x{entry.get('count', 1)}")
        
        if not card_entries:
            return jsonify({"error": "Nessuna carta fornita"}), 400
        
        # Crea PDF temporaneo su disco
        pdf_fd, pdf_path = tempfile.mkstemp(suffix='.pdf')
        os.close(pdf_fd)  # Chiudi il file descriptor
        
        pdf = FPDF(unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=10)
        
        temp_images = []
        total_cards_added = 0
        
        try:
            for entry in card_entries:
                name = entry.get("name", "").strip()
                count = int(entry.get("count", 1))
                
                if not name:
                    continue
                    
                print(f"🔄 Processando: {name} (x{count})")
                
                image_url = get_card_image_url(name)
                if not image_url:
                    print(f"❌ Nessun URL per {name}")
                    continue
                
                try:
                    # Scarica immagine
                    print(f"⬇️ Scaricando: {image_url}")
                    img_response = requests.get(image_url, timeout=15)
                    img_response.raise_for_status()
                    
                    print(f"📦 Dimensione immagine: {len(img_response.content)} bytes")
                    
                    # Processa immagine
                    img = Image.open(BytesIO(img_response.content))
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Ridimensiona mantenendo proporzioni
                    target_width, target_height = 540, 750  # 180*3, 250*3 per qualità
                    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    # Salva immagine temporanea
                    img_fd, img_path = tempfile.mkstemp(suffix='.jpg')
                    os.close(img_fd)
                    temp_images.append(img_path)
                    
                    img.save(img_path, format='JPEG', quality=95, optimize=True)
                    print(f"💾 Immagine salvata: {img_path}")
                    
                    # Aggiungi al PDF
                    for i in range(count):
                        pdf.add_page()
                        pdf.image(img_path, x=15, y=15, w=180, h=250)
                        total_cards_added += 1
                        print(f"➕ Aggiunta carta {total_cards_added}: {name} ({i+1}/{count})")
                    
                except requests.RequestException as e:
                    print(f"❌ Errore download {name}: {e}")
                    continue
                except Exception as e:
                    print(f"❌ Errore processamento {name}: {e}")
                    continue
            
            if total_cards_added == 0:
                return jsonify({"error": "Nessuna carta è stata aggiunta al PDF"}), 400
            
            # Genera PDF
            print(f"📄 Generando PDF con {total_cards_added} carte...")
            pdf.output(pdf_path)
            
            # Verifica che il file esista e non sia vuoto
            if not os.path.exists(pdf_path):
                return jsonify({"error": "File PDF non creato"}), 500
                
            pdf_size = os.path.getsize(pdf_path)
            print(f"✅ PDF creato: {pdf_path} ({pdf_size} bytes)")
            
            if pdf_size == 0:
                return jsonify({"error": "PDF vuoto generato"}), 500
            
            # Invia il file
            return send_file(
                pdf_path,
                as_attachment=True,
                download_name='carte.pdf',
                mimetype='application/pdf'
            )
            
        finally:
            # Pulizia file temporanei immagini
            for img_path in temp_images:
                try:
                    if os.path.exists(img_path):
                        os.unlink(img_path)
                        print(f"🗑️ Rimossa immagine temporanea: {img_path}")
                except Exception as e:
                    print(f"⚠️ Errore rimozione {img_path}: {e}")
            
            # Il PDF temporaneo verrà rimosso automaticamente da Flask dopo send_file
            
    except Exception as e:
        print(f"💥 Errore generale: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Errore interno: {str(e)}"}), 500

@app.route('/debug', methods=['POST'])
def debug_cards():
    """Endpoint per debuggare senza generare PDF"""
    content = request.json
    card_entries = content.get("cards", [])
    
    results = []
    for entry in card_entries:
        name = entry.get("name")
        image_url = get_card_image_url(name)
        results.append({
            "name": name,
            "normalized": normalize_card_name(name),
            "image_url": image_url,
            "found": image_url is not None
        })
    
    return jsonify({"results": results})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
