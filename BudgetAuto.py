from flask import Flask, request, jsonify
import math, os

# ------------------------------
# Your existing pricing engine
# ------------------------------
class MarinaRates:
    def __init__(self, rates_table):
        self.rates_table = rates_table
        self.vat = 1.21
        self.catamaran_multiplier = 1.7

    def get_fixed_percentage(self, days):
        if days <= 90:
            return 0.36
        elif days <= 180:
            return 0.29
        elif days <= 365:
            return 0.26
        else:
            return 0.25

    def calculate_base_price(self, length, days, vessel_type, beam=None):
        available_lengths = sorted(self.rates_table["DAILY"].keys())

        if 20 < length < 25:
            effective_length = 25
        elif 30 < length < 35:
            effective_length = 35
        else:
            effective_length = next((l for l in available_lengths if l >= math.ceil(length)), max(length, 7))

        # Vessels >35 meters use dynamic calculation
        if effective_length > 35 and beam is not None:
            fixed_percentage = self.get_fixed_percentage(days)
            base_price = fixed_percentage * effective_length * beam * days
        else:
            if days == 90:
                base_price = self.rates_table["3_MONTHS"].get(effective_length, None)
            elif days == 180:
                base_price = self.rates_table["6_MONTHS"].get(effective_length, None)
            elif days == 365:
                base_price = self.rates_table["ANNUAL"].get(effective_length, None)
            else:
                if days <= 90:
                    daily_rate = self.rates_table["DAILY"].get(effective_length, None)
                    base_price = daily_rate * days if daily_rate else None
                elif days <= 180:
                    daily_rate = self.rates_table["3_MONTHS"].get(effective_length, None) / 90
                    base_price = daily_rate * days if daily_rate else None
                elif days <= 365:
                    daily_rate = self.rates_table["6_MONTHS"].get(effective_length, None) / 180
                    base_price = daily_rate * days if daily_rate else None
                else:
                    daily_rate = self.rates_table["ANNUAL"].get(effective_length, None) / 365
                    base_price = daily_rate * days if daily_rate else None

        if base_price is None:
            return None

        if vessel_type.lower() == "catamaran":
            base_price *= self.catamaran_multiplier

        return base_price

    def calculate_taxes(self, length, beam, days, stay_type, vessel_type=None):
        T0 = 0
        T5 = 0

        if vessel_type:
            vessel_type = vessel_type.lower()

        # Apply T0 only to:
        if (vessel_type in ["monohull", "catamaran"] and length >= 12) or (vessel_type == "motorboat" and length >= 9):
            if stay_type == "short":
                T0 = length * beam * days * 0.0250
            else:
                T0 = length * beam * 9.12

        # Apply T5 to all vessels
        if length < 12:
            if stay_type == "short":
                T5 = length * beam * days * 0.186
            else:
                T5 = length * beam * days * 0.124
        else:
            if stay_type == "short":
                T5 = length * beam * days * 0.0397
            else:
                T5 = length * beam * days * 0.0397

        return {"T0": round(T0, 2), "T5": round(T5, 2)}

    def get_final_quote(self, length, beam, days, vessel_type, stay_type):
        base_price_no_vat = self.calculate_base_price(length, days, vessel_type, beam)
        if base_price_no_vat is None:
            return "Error: Invalid length or rates not found."

        taxes = self.calculate_taxes(length, beam, days, stay_type, vessel_type)
        T0 = taxes["T0"]
        T5 = taxes["T5"]
        total_taxes = T0 + T5

        total_no_vat = base_price_no_vat + total_taxes
        final_price = total_no_vat * self.vat

        return {
            "Base Price (No VAT)": round(base_price_no_vat, 2),
            "T0": round(T0, 2),
            "T5": round(T5, 2),
            "Total Taxes": round(total_taxes, 2),
            "Total (With VAT)": round(final_price, 2),
        }

rates_table_no_vat = {
    "DAILY": {
        7: 8.18, 8: 9.26, 9: 10.33, 10: 13.22, 11: 15.29, 12: 16.94, 13: 18.79, 14: 20.47,
        15: 26.05, 16: 28.10, 17: 30.39, 18: 32.23, 19: 33.50, 20: 36.36, 25: 48.76,
        30: 58.68, 35: 71.07
    },
    "3_MONTHS": {
        7: 681.82, 8: 739.67, 9: 805.75, 10: 929.75, 11: 1117.36, 12: 1301.65, 13: 1383.50,
        14: 1512.40, 15: 1652.89, 16: 1776.69, 17: 1921.49, 18: 2066.12, 19: 2290.91,
        20: 2602.48, 25: 3314.05, 30: 4545.45, 35: 5371.90
    },
    "6_MONTHS": {
        7: 1239.67, 8: 1392.56, 9: 1487.60, 10: 1776.86, 11: 2045.45, 12: 2396.69, 13: 2520.66,
        14: 2735.54, 15: 3123.97, 16: 3264.46, 17: 3636.36, 18: 3933.88, 19: 4132.23,
        20: 4934.71, 25: 6297.52, 30: 8437.19, 35: 9722.31
    },
    "ANNUAL": {
        7: 2272.73, 8: 2493.39, 9: 2561.98, 10: 3016.53, 11: 3574.38, 12: 4132.23, 13: 4561.98,
        14: 4851.24, 15: 5454.55, 16: 5892.56, 17: 6257.02, 18: 6735.54, 19: 7272.73,
        20: 8483.47, 25: 11322.31, 30: 14235.54, 35: 16528.93
    }
}

# ------------------------------
# API wrapper for n8n
# ------------------------------
app = Flask(__name__)
marina_rates = MarinaRates(rates_table_no_vat)

API_KEY = os.getenv("ESTIMATOR_API_KEY", "").strip()  # optional

def _bad(msg):
    # Return ok:false with 200 so n8n HTTP node doesn't hard-fail
    return jsonify({"ok": False, "error": msg}), 200

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})

@app.post("/estimate")
def estimate():
    # optional API key via header X-API-Key
    if API_KEY and request.headers.get("X-API-Key", "").strip() != API_KEY:
        return _bad("unauthorized")

    data = request.get_json(silent=True) or {}
    try:
        length = float(data.get("length_m") or data.get("length") or 0)
        beam   = float(data.get("beam_m") or data.get("beam") or 0)
        days   = int(data.get("days") or 0)
        vessel_type = (data.get("vessel_type") or "monohull").strip().lower()
    except Exception:
        return _bad("bad input")

    # sanity ranges (align with your n8n checks)
    if not (3 <= length <= 200): return _bad("length_m out of range")
    if not (1 <= beam <= 30):    return _bad("beam_m out of range")
    if not (1 <= days <= 365):   return _bad("days out of range")

    stay_type = "short" if days < 183 else "long"

    quote = marina_rates.get_final_quote(length, beam, days, vessel_type, stay_type)
    if isinstance(quote, str):
        return _bad(quote)

    pricing = {
        "base_no_vat": quote["Base Price (No VAT)"],
        "t0": quote["T0"],
        "t5": quote["T5"],
        "taxes": quote["Total Taxes"],
        "total_with_vat": quote["Total (With VAT)"],
        "currency": "EUR"
    }
    return jsonify({"ok": True, "pricing": pricing}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=True)
