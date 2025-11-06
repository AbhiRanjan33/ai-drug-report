# 🩺 Clinical Summary & Alerter Tool (LLM Version)

This project uses a Python backend to power a smart "Clinical Summary Tool." The frontend (HTML) captures a patient's profile, and the backend (Python/Flask) uses the Gemini LLM to analyze that profile against official openFDA drug data to generate safety alerts.

## How it Works

1.  **Frontend (`index.html`)**: The user enters a patient's profile (notes, allergies, meds).
2.  When "Generate Report" is clicked, the frontend sends this profile (as JSON) to the local Python backend (`http://127.0.0.1:5000`).
3.  **Backend (`app.py`)**:
    * Receives the patient profile.
    * Securely fetches the secret **Gemini API Key** from your `.env` file.
    * Fetches official drug data from the **openFDA API** for a list of common hypertension drugs.
    * For *each drug*, it constructs a prompt containing both the patient's profile and the drug's technical data (contraindications, warnings, etc.).
    * It sends this prompt to the **Gemini LLM** and asks it to "act as a clinical pharmacologist" and identify *all* potential conflicts in a specific JSON format.
    * It collects all the LLM's findings and sends them back to the frontend.
4.  **Frontend (`index.html`)**: Receives the JSON report from the backend and displays the alerts for the user.

## How to Set Up and Run

### Step 1: Get Your API Key

1.  You need a Gemini API key. Go to [Google AI Studio](https://aistudio.google.com/app/apikey) to create one.
2.  This key is **secret**. Do not share it.

### Step 2: Set Up the Backend (Python)

1.  **Create an Environment File**:
    * In the same folder as these files, create a new file named `.env`
    * Copy the contents of `.env.example` into it and paste your API key:
    ```
    GEMINI_API_KEY=YOUR_SECRET_API_KEY_GOES_HERE
    ```

2.  **Install Python Libraries**:
    * Make sure you have Python 3.7+ installed.
    * Open your terminal or command prompt in this project's folder.
    * Install the required libraries:
    ```sh
    pip install -r requirements.txt
    ```

3.  **Run the Backend Server**:
    * In your terminal, run the following command:
    ```sh
    python app.py
    ```
    * You should see a message like `* Running on http://127.0.0.1:5000`. This means your backend is working. **Keep this terminal open.**

### Step 3: Run the Frontend (HTML)

1.  **Open `index.html`**: In a *new* terminal or file explorer, find the `index.html` file.
2.  **Open in Browser**: Double-click `index.html` to open it in your web browser (like Chrome or Firefox).

You can now use the application! Enter the patient data and click "Generate Summary Report." The HTML page will communicate with your local Python server (at `http://127.0.0.1:5000`) and display the LLM-generated results.