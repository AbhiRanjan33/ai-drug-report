import os
import requests
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import time

# --- Configuration ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Please check your .env file.")

# --- "AI Brain" Configuration ---

# 1. Define the JSON schema we want the LLM to return
response_schema = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "type": {
                "type": "STRING",
                "enum": ["🔴 CONTRAINDICATION", "🟠 WARNING", "🟡 INTERACTION", "🟠 SIDE EFFECT MATCH", "🟢 INFO"]
            },
            "finding": {
                "type": "STRING",
                "description": "A concise, one-sentence explanation of the conflict, side effect, or interaction found."
            }
        },
        "required": ["type", "finding"]
    }
}

# 2. Define the system prompt (the LLM's instructions)
system_prompt = f"""
You are an expert clinical pharmacologist's assistant. Your sole purpose is to
read a patient's profile and cross-reference it with the full text of a drug's
official "Contraindications", "Warnings", "Interactions", and "Adverse Reactions".

You must be extremely thorough. Find every potential conflict, even minor ones.
- 🔴 CONTRAINDICATION: A direct "do not use" situation. (e.g., a listed allergy, a pre-existing condition in contraindications).
- 🟠 WARNING: A "use with caution" situation. (e.g., patient has 'diabetes' and the drug warns about 'diabetic patients').
- 🟡 INTERACTION: A conflict with one of the patient's other medications.
- 🟠 SIDE EFFECT MATCH: The patient's notes (symptoms) match a known adverse reaction.
- 🟢 INFO: No conflicts found.

You MUST respond only with the JSON schema provided.
Do not add any other text or explanation.
"""

# 3. Define the generation config, including the schema
generation_config = {
    "response_mime_type": "application/json",
    "response_schema": response_schema
}

# 4. Configure the Gemini API and Model
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "gemini-2.0-flash", # Using a known, stable model
    generation_config=generation_config,
    system_instruction=system_prompt
)


# --- Flask App Setup ---
app = Flask(_name_)
CORS(app) # Enable CORS

# --- "AI" KNOWLEDGE BASE ---
COMMON_BP_DRUGS = [
    {"class": "ACE Inhibitor", "name": "Lisinopril"},
    {"class": "ARB", "name": "Losartan"},
    {"class": "Calcium Channel Blocker", "name": "Amlodipine"},
    {"class": "Beta-Blocker", "name": "Metoprolol"},
    {"class": "Diuretic", "name": "Hydrochlorothiazide"}
]

# --- Helper Functions ---

def fetch_drug_data(drug_name):
    """Fetches drug data from openFDA."""
    search_field = f'(openfda.generic_name.exact:"{drug_name.upper()}" OR openfda.brand_name.exact:"{drug_name.upper()}")'
    url = f"https://api.fda.gov/drug/label.json?search={search_field}&limit=1"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("error") or not data.get("results"):
            print(f"No results found for {drug_name}")
            return None
            
        drug = data["results"][0]
        
        def get_section_text(section_key):
            section_data = drug.get(section_key)
            if isinstance(section_data, list) and section_data:
                return " ".join(section_data).lower()
            return "No information listed."

        return {
            "brandName": ", ".join(drug.get("openfda", {}).get("brand_name", ["N/A"])),
            "genericName": ", ".join(drug.get("openfda", {}).get("generic_name", [drug_name])),
            "contraindications": get_section_text("contraindications"),
            "warnings_and_precautions": get_section_text("warnings_and_precautions"),
            "drugInteractions": get_section_text("drug_interactions"),
            "adverseReactions": get_section_text("adverse_reactions")
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {drug_name}: {e}")
        return None

def analyze_with_llm(patient_profile_text, drug_data):
    """
    Uses the Gemini LLM to analyze the patient profile against the drug data.
    """
    user_prompt = f"""
    PATIENT PROFILE:
    {patient_profile_text}

    DRUG DATA FOR: {drug_data['genericName']}
    ---
    CONTRAINDICATIONS:
    {drug_data['contraindications']}
    ---
    WARNINGS AND PRECAUTIONS:
    {drug_data['warnings_and_precautions']}
    ---
    DRUG INTERACTIONS:
    {drug_data['drugInteractions']}
    ---
    ADVERSE REACTIONS:
    {drug_data['adverseReactions']}
    ---
    ANALYZE and return all conflicts. If no conflicts are found, return a single "INFO" alert.
    """
    
    max_retries = 3
    delay = 1
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(user_prompt)
            alerts = json.loads(response.text)
            return alerts

        except Exception as e:
            print(f"Error calling LLM on attempt {attempt + 1}: {e}")
            raw_response = "No response object"
            if "response" in locals():
                try:
                    raw_response = response.text
                except Exception:
                    raw_response = "Could not get response.text"
            print(f"LLM Response (raw): {raw_response}")
            
            if "429" in str(e) or "503" in str(e):
                print(f"Rate limit or server error. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                return [{"type": "🔴 ERROR", "finding": f"Could not analyze drug: {str(e)}"}]

    return [{"type": "🔴 ERROR", "finding": "Could not analyze drug after multiple retries."}]

def get_profile_text(profile):
    """Helper function to convert patient profile JSON to text for the LLM."""
    return f"""
    - Vitals: {profile.get('vitals', 'N/A')}
    - Notes/History: {profile.get('notes', 'N/A')}
    - Allergies: {', '.join(profile.get('allergies', [])) or 'N/A'}
    - Other Medications: {', '.join(profile.get('meds', [])) or 'N/A'}
    """

# --- API Endpoints ---

@app.route('/generate-report', methods=['POST'])
def generate_report():
    """Generates the main summary report for the default list of BP drugs."""
    try:
        profile = request.json
        if not profile:
            return jsonify({"error": "No patient profile provided"}), 400
            
        profile_text = get_profile_text(profile)
        all_reports = []

        for drug_def in COMMON_BP_DRUGS:
            drug_name = drug_def["name"]
            drug_data = fetch_drug_data(drug_name)
            
            if not drug_data:
                report = {
                    "genericName": drug_name,
                    "brandName": "N/A",
                    "drugClass": drug_def["class"],
                    "alerts": [{"type": "🔴 ERROR", "finding": "Could not fetch drug data from openFDA."}],
                    "fullData": {}
                }
                all_reports.append(report)
                continue
            
            alerts = analyze_with_llm(profile_text, drug_data)
            
            report = {
                "genericName": drug_data["genericName"],
                "brandName": drug_data["brandName"],
                "drugClass": drug_def["class"],
                "alerts": alerts,
                "fullData": drug_data
            }
            all_reports.append(report)

        return jsonify(all_reports)

    except Exception as e:
        print(f"An error occurred in /generate-report: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/check-drug', methods=['POST'])
def check_single_drug():
    """Checks a single, custom drug name against the patient profile."""
    try:
        data = request.json
        if not data or 'profile' not in data or 'drugName' not in data:
            return jsonify({"error": "Missing profile or drugName"}), 400

        profile = data['profile']
        drug_name = data['drugName']
        profile_text = get_profile_text(profile)

        # 1. Fetch drug data
        drug_data = fetch_drug_data(drug_name)
        if not drug_data:
            return jsonify({
                "genericName": drug_name,
                "brandName": "N/A",
                "drugClass": "Custom Search",
                "alerts": [{"type": "🔴 ERROR", "finding": f"Could not fetch drug data for '{drug_name}'. Check spelling."}],
                "fullData": {}
            })
        
        # 2. Analyze with LLM
        alerts = analyze_with_llm(profile_text, drug_data)
        
        # 3. Build and return report
        report = {
            "genericName": drug_data["genericName"],
            "brandName": drug_data["brandName"],
            "drugClass": "Custom Search", # We don't know the class for a custom search
            "alerts": alerts,
            "fullData": drug_data
        }
        return jsonify(report)

    except Exception as e:
        print(f"An error occurred in /check-drug: {e}")
        return jsonify({"error": str(e)}), 500

# --- Run the App ---
if _name_ == '_main_':
    print("Starting Flask server...")
    print("Your backend is running at http://127.0.0.1:5000")
    print("Open the index.html file in your browser to use the app.")
    app.run(port=5000, debug=False)