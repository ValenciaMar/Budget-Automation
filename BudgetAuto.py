from flask import Flask, request, jsonify
import re
import os

app = Flask(__name__)

def extract_info(text):
    text = text.lower()

    # ---------- Intent detection ----------
    if any(word in text for word in ["reservar", "book", "réserver"]):
        intent = "booking_request"
    elif any(word in text for word in ["precio", "price", "tarif", "coût", "cuánto"]):
        intent = "price_inquiry"
    else:
        intent = "general_info"

    # ---------- Boat size ----------
    size_match = re.search(r"(\d{1,2})\s?(m|metros|meters|mètres)", text)
    boat_size = size_match.group(0) if size_match else None

    # ---------- Dates ----------
    date_patterns = [
        r"del\s\d{1,2}\s(?:al|-)\s\d{1,2}\sde\s[a-z]+",     # Spanish
        r"from\s\d{1,2}\s(?:to|-)\s\d{1,2}\s[a-z]+",        # English
        r"du\s\d{1,2}\s(?:au|-)\s\d{1,2}\s[a-zéèê]+"        # French
    ]

    dates = None
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            dates = match.group(0)
            break

    # ---------- Email address ----------
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    email = email_match.group(0) if email_match else None

    return {
        "intent": intent,
        "boat_size": boat_size,
        "dates": dates,
        "email": email
    }

@app.route('/parse', methods=['POST'])
def parse():
    content = request.json.get('text', '')
    result = extract_info(content)
    return jsonify(result)

# ✅ This must come LAST — and only run when hosted
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
