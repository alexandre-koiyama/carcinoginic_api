import io
from flask import Flask, request, jsonify
from PIL import Image
from google import genai
from google.api_core.exceptions import ResourceExhausted
import cred
import json
from datetime import datetime


GOOGLE_API_KEY = cred.gooogle_api_key
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY environment variable is not set")

client = genai.Client(api_key=GOOGLE_API_KEY)

app = Flask(__name__)

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"}), 200


def update_daily_count():
    today = datetime.now().strftime("%Y-%m-%d")
    COUNT_FILE = "/Users/alexandrekoiyama/Desktop/PROJECTS/carcinogenic_new/daily_calls.json"

    try:
        with open(COUNT_FILE) as f:
            data = json.load(f)
    except:
        data = {}

    data[today] = data.get(today, 0) + 1

    with open(COUNT_FILE, "w") as f:
        json.dump(data, f, indent=2)


###########################################################################################3
@app.route("/analyze", methods=["POST"])
def analyze_image():

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    try:
        update_daily_count()

        # ---- Read image ----
        file = request.files["file"]
        image = Image.open(io.BytesIO(file.read())).convert("RGB")

        img_buffer = io.BytesIO()
        image.save(img_buffer, format="PNG")
        img_bytes = img_buffer.getvalue()

        # ---- Load IARC reference table ----
        with open(
            "/Users/alexandrekoiyama/Desktop/PROJECTS/carcinogenic_new/carcinogens.csv",
            "r",
            encoding="utf-8"
        ) as f:
            csv_content = f.read()

        prefer_language = "En"

        prompt = (
        "CRITICAL OUTPUT RULES:\n"
            "- Output MUST be a single valid JSON object.\n"
            "- Do NOT use markdown.\n"
            "- Do NOT include ``` or formatting.\n"
            "- Do NOT include explanations, legends, emojis, or text outside JSON.\n"
            "- If you violate these rules, the response is INVALID.\n\n"

        "You are a toxicologist and regulatory analyst expert in evaluating product safety, "
        "especially based on the IARC Monographs on the Evaluation of Carcinogenic Risks to Humans.\n\n"
        "Your job is to extract all ingredients from the product label image and classify each one "
        "according to IARC Monographs Group 1, 2A, 2B, or 3.\n"

        "If the ingredient name is commercial, brand-based, abbreviated (e.g., E-numbers), or a common term, "
        "identify the equivalent scientific or chemical name from the IARC list provided.\n\n"

        "Use this IARC reference table for classification (chemical name | group | explanation):\n"
        f"{csv_content}\n\n"

        "TASK:\n"
        "1. Detect the language of the label.\n"
        "2. Extract every ingredient visible in the image.\n"
        "3. Map each ingredient to the closest scientific or chemical name if needed.\n"
        "4. Match the ingredient to the IARC reference table.\n"
        "5. If the ingredient is not present in the table, classify it as Group 3.\n\n"

        "OUTPUT FORMAT (STRICT JSON ONLY):\n"
        "{"
        '  "language": "Detected language of the image text",'
        '  "ingredients": ['
        "    {"
        '      "name": "Ingredient name exactly as detected or normalizedn",'
        '      "name_preferred": f"Ingredient name translated to {prefer_language}",'
        '      "group": "1 | 2A | 2B | 3",'
        '      "explanation": "Maximum 18 words describing what it is and common uses. If group is 1, 2A, or 2B include a short risk note."'
        "    }]}"
        )

        # ---- Call Gemini ----
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                prompt,
                genai.types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/png"
                )
            ]
        )

        # ---- HARD JSON CLEANING ----
        raw_text = response.text.strip()

        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1

        if start == -1 or end == -1:
            return jsonify({
                "error": "Model did not return valid JSON"
            }), 500

        clean_json_text = raw_text[start:end]
        data = json.loads(clean_json_text)

        data["source"] = (
            "The analysis is based on the IARC Monographs on the Evaluation of Carcinogenic Risks to Humans. "
            "Group 1: carcinogenic to humans with sufficient evidence. "
            "Group 2A: probably carcinogenic with limited human evidence and sufficient animal evidence. "
            "Group 2B: possibly carcinogenic with limited human evidence and insufficient animal evidence. "
            "Group 3: not classifiable as to carcinogenicity due to inadequate evidence."
        )

        data["legend"] = [
            {"color": "#FF0000", "group": "1", "name": "Group 1",
             "description": "Carcinogenic to humans: sufficient evidence in humans."},
            {"color": "#eb8627", "group": "2A", "name": "Group 2A",
             "description": "Probably carcinogenic: limited human evidence, sufficient animal evidence."},
            {"color": "#d3b221", "group": "2B", "name": "Group 2B",
             "description": "Possibly carcinogenic: limited human evidence, insufficient animal evidence."},
            {"color": "#299432", "group": "3", "name": "Group 3",
             "description": "Not classifiable as carcinogenic or not listed."}
        ]

        data["prefer_language"] = prefer_language

        return jsonify(data), 200

    except ResourceExhausted:
        return jsonify({
            "error": "Gemini API quota exceeded. Please try again later."
        }), 429

    except json.JSONDecodeError:
        return jsonify({
            "error": "Invalid JSON returned by model"
        }), 500

    except Exception as e:
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500



@app.route("/analyze", methods=["GET", "PUT", "DELETE", "PATCH"])
def analyze_blocked():
    return jsonify({"error": "Method not allowed"}), 405



if __name__ == "__main__":
    app.run(debug=True)