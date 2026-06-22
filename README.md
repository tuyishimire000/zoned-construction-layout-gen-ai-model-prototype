# Smart Building Compliance & Floor Plan Prototype

An intelligent building compliance assessment system. It uses NLP to extract project parameters from natural language, evaluates compliance against Kigali/Gasabo mock regulations, and automatically generates a schematic floor plan and compliance report.

## Tech Stack
- **Backend:** Python 3.12, FastAPI, spaCy, Pillow
- **Frontend:** React (Vite), CSS

## Setup Instructions

### 1. Backend Setup
1. Open a terminal and navigate to the `backend/` directory.
2. Ensure you have Python installed.
3. Activate the virtual environment:
   ```bash
   .\venv\Scripts\activate
   ```
4. Start the FastAPI server:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   *The API will be available at http://localhost:8000*

### 2. Frontend Setup
1. Open a new terminal and navigate to the `frontend/` directory.
2. Start the Vite development server:
   ```bash
   npm run dev
   ```
3. Open the URL provided in the terminal (usually http://localhost:5173) in your browser.

## Features
- **Natural Language Input**: Describe your project normally (e.g., "600 sqm residential plot with three floors").
- **Real-time Assessment**: See if your project passes or fails zoning rules instantly.
- **Interactive Refinement**: Adjust parameters with sliders and instantly see the report and floor plan update.
- **Auto Floor Plan**: A dynamic PNG is generated reflecting the building footprint and parking.
