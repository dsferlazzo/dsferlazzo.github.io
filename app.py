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
        
        response = requests.get(f"{API_BASE}/cards/" + normalized_name, timeout=10)
        print(f"📡 API Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Errore API per {normalized_name}: {response.status_code}")
            return None
            
        data = response.json()
        print(f"📊 Dati ricevuti: {bool(data and data.get('data'))}")
        
        if data and data.get("editions"):
            print(f"📋 Card data keys: {list(data.keys())}")
            print(f"📛 Card name: {data.get('name', 'N/A')}")
            
            editions = data.get("editions", [])
            print(f"📦 Editions trovate: {len(editions)}")
            
            if editions and len(editions) > 0:
                first_edition = editions[0]
                print(f"🎨 Prima edition keys: {list(first_edition.keys())}")
                
                if first_edition.get("image"):
                    image_path = first_edition["image"]
                    full_image_url = API_BASE + image_path
                    print(f"🖼️ URL immagine: {full_image_url}")
                    return full_image_url
                else:
                    print(f"❌ Nessun campo 'image' nella prima edition")
                    print(f"🔍 Edition completa: {first_edition}")
            else:
                print(f"❌ Nessuna edition trovata")
        else:
            print(f"❌ Nessun campo 'editions' nell'API response")
            print(f"📄 Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            print(f"📄 Response preview: {str(data)[:300]}...")
            
                
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
        card_name = "Merlin, Kingslayer"
        normalized_name = normalize_card_name(card_name)
        response = requests.get(f"{API_BASE}/cards/" + normalized_name, timeout=10)
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
        pdf.set_auto_page_break(auto=False)  # Disabilita page break automatico per controllo manuale
        
        temp_images = []
        total_cards_processed = 0
        
        # Dimensioni carta in mm - 6.4cm x 8.9cm
        CARD_WIDTH = 64  # 6.4 cm
        CARD_HEIGHT = 89  # 8.9 cm
        
        # Layout griglia 3x3
        CARDS_PER_ROW = 3
        CARDS_PER_COL = 3
        CARDS_PER_PAGE = CARDS_PER_ROW * CARDS_PER_COL  # 9 carte per pagina
        
        # Calcola margini per centrare la griglia nella pagina A4 (210x297mm)
        PAGE_WIDTH = 210
        PAGE_HEIGHT = 297
        GRID_WIDTH = CARDS_PER_ROW * CARD_WIDTH  # 192mm
        GRID_HEIGHT = CARDS_PER_COL * CARD_HEIGHT  # 267mm
        
        START_X = (PAGE_WIDTH - GRID_WIDTH) / 2  # Centra orizzontalmente
        START_Y = (PAGE_HEIGHT - GRID_HEIGHT) / 2  # Centra verticalmente
        
        print(f"📐 Layout: {CARDS_PER_ROW}x{CARDS_PER_COL} = {CARDS_PER_PAGE} carte per pagina")
        print(f"📐 Dimensioni carta: {CARD_WIDTH}x{CARD_HEIGHT}mm")
        print(f"📐 Margini: START_X={START_X:.1f}mm, START_Y={START_Y:.1f}mm")
        
        # Lista di tutte le carte da stampare (espanse per quantità)
        all_cards = []
        for entry in card_entries:
            name = entry.get("name", "").strip()
            count = int(entry.get("count", 1))
            
            if not name:
                continue
            
            for _ in range(count):
                all_cards.append(name)
        
        print(f"📋 Totale carte da stampare: {len(all_cards)}")
        
        # Processa le carte e scarica le immagini
        card_images = {}  # Cache delle immagini per evitare download multipli
        
        try:
            for i, card_name in enumerate(all_cards):
                if card_name not in card_images:
                    print(f"🔄 Processando carta {card_name} ({i+1}/{len(all_cards)})")
                    
                    image_url = get_card_image_url(card_name)
                    if not image_url:
                        print(f"❌ Nessun URL per {card_name}")
                        continue
                    
                    try:
                        # Scarica immagine
                        print(f"⬇️ Scaricando: {image_url}")
                        img_response = requests.get(image_url, timeout=15)
                        img_response.raise_for_status()
                        
                        # Processa immagine
                        img = Image.open(BytesIO(img_response.content))
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Ridimensiona per la stampa (risoluzione 300 DPI)
                        # 6.4cm @ 300 DPI = 756 pixels, 8.9cm @ 300 DPI = 1051 pixels
                        target_width = int(6.4 * 300 / 2.54)  # ~756px
                        target_height = int(8.9 * 300 / 2.54)  # ~1051px
                        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                        
                        # Salva immagine temporanea
                        img_fd, img_path = tempfile.mkstemp(suffix='.jpg')
                        os.close(img_fd)
                        temp_images.append(img_path)
                        
                        img.save(img_path, format='JPEG', quality=95, optimize=True)
                        card_images[card_name] = img_path
                        print(f"💾 Immagine cached: {card_name}")
                        
                    except requests.RequestException as e:
                        print(f"❌ Errore download {card_name}: {e}")
                        continue
                    except Exception as e:
                        print(f"❌ Errore processamento {card_name}: {e}")
                        continue
            
            # Ora crea le pagine PDF con layout griglia
            cards_on_current_page = 0
            
            for i, card_name in enumerate(all_cards):
                if card_name not in card_images:
                    continue
                
                # Inizia una nuova pagina se necessario
                if cards_on_current_page == 0:
                    pdf.add_page()
                    print(f"📄 Nuova pagina PDF")
                
                # Calcola posizione nella griglia
                row = cards_on_current_page // CARDS_PER_ROW
                col = cards_on_current_page % CARDS_PER_ROW
                
                x = START_X + (col * CARD_WIDTH)
                y = START_Y + (row * CARD_HEIGHT)
                
                # Aggiungi carta al PDF
                pdf.image(card_images[card_name], x=x, y=y, w=CARD_WIDTH, h=CARD_HEIGHT)
                
                total_cards_processed += 1
                cards_on_current_page += 1
                
                print(f"➕ Carta {total_cards_processed}: {card_name} -> pos({col},{row}) @ ({x:.1f},{y:.1f})mm")
                
                # Reset contatore se pagina piena
                if cards_on_current_page >= CARDS_PER_PAGE:
                    cards_on_current_page = 0
            
            if total_cards_processed == 0:
                return jsonify({"error": "Nessuna carta è stata aggiunta al PDF"}), 400
            
            # Genera PDF
            print(f"📄 Generando PDF con {total_cards_processed} carte...")
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
