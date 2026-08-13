# 🥗 Smart Pantry & Recipe Concierge

> A conversational AI agent that helps home cooks catalog ingredients from receipts/photos, track daily pantry inventory in Cloud Firestore, and generate personalized weekly meal plans, shopping lists, and dish media previews.

![Smart Pantry Demo](smart_pantry_demo.gif)

## 🌟 Key Features

- **🧾 Receipt & Photo Ingredient Cataloging**: Extract ingredients directly from receipt photos or fridge snapshots and automatically populate your Firestore inventory.
- **📦 Firestore Inventory Management**: Real-time tracking of pantry items, quantities, expiration dates, and automatic item deductions when meals are prepared.
- **📖 Grounded Historic Recipe RAG**: Grounded culinary recommendations sourced from the 1814 *Domestic Cookery* historic cookbook corpus via Vertex AI RAG Engine.
- **🎨 Imagen Dish Photography & Omni Video Previews**: Studio-quality dish photography (`gemini-3.1-flash-lite-image`) and 5-second video previews (`gemini-omni-flash-preview`) hosted on Google Cloud Storage.
- **🧮 Sandbox Macro & Portion Math**: In-sandboxed Python code execution (`AgentEngineSandboxCodeExecutor`) to calculate precise calorie/macro totals and recipe yield adjustments.
- **✨ Interactive A2UI Surfaces**: Rich, responsive component cards (A2UI v0.8) for displaying current inventory, meal plans, and grocery checklists.
- **🧠 Cross-Session Memory Bank**: Persistent long-term memory via Vertex AI Memory Bank to remember user food allergies, dietary restrictions, and cooking preferences across conversations.

## ☁️ Google Cloud & Vertex AI Architecture

| Tool / Technology | Purpose in Smart Pantry |
| :--- | :--- |
| **Vertex AI Memory Bank** | Long-term cross-session memory for user dietary preferences and allergies |
| **Cloud Firestore** | Real-time NoSQL database for pantry inventory (`pantry_inventory` collection) |
| **Cloud Storage (GCS)** | Public storage bucket serving dish images and video previews via HTTPS URLs |
| **Vertex AI RAG Engine** | Vector search and document grounding against the 1814 Historic Cookbook corpus |
| **Vertex AI Image & Video Gen** | Generates dish images (`gemini-3.1-flash-lite-image`) and video previews (`gemini-omni-flash-preview`) |
| **Agent Engine Sandbox** | Isolated Python execution sandbox for calorie, macro, and yield calculations |
| **A2UI Schema Manager** | A2UI v0.8 renderer for structured card and list components in the chat UI |
| **Cloud Run & Agent Platform** | FastAPI proxy deployed on Cloud Run communicating via A2A protocol to Agent Runtime |

## 🚀 Getting Started Locally

### Prerequisites
- Python 3.12+
- Node.js 18+
- Google Cloud SDK (`gcloud`) with ADC initialized

### Running the App
1. **Start the Frontend Proxy & UI**:
   ```bash
   cd frontend
   pip install -r requirements.txt
   export AGENT_ENGINE_RESOURCE_NAME="projects/135622055779/locations/us-east1/reasoningEngines/4121585307416002560"
   export AGENT_DIRECTORY="app"
   python main.py
   ```
2. Open `http://localhost:8080` in your browser.
