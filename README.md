# Smart Building Compliance & Floor Plan Prototype

An intelligent building compliance assessment and generative layout system. It uses Generative AI to interpret natural language architectural requests, evaluates the project against Kigali/Gasabo zoning and sanitation regulations, and automatically generates a physics-based, compliant schematic floor plan.

##  Key Features

- **Generative AI Natural Language Input**: Describe your project requirements normally (e.g., "A modern 3-bedroom house with a master suite, kitchen, and outside boy's quarters"). The system uses the Google Gemini API to extract room counts, graph connectivity, and plot parameters.
- **Physics-Based Layout Engine**: Uses a custom force-directed graph physics engine to automatically arrange rooms based on mathematical constraints, minimizing overlap while keeping logically connected rooms attached.
- **Auto-Routing & Compliance Fixes**: The internal AI Graph Validator automatically inspects the generated layout graph for privacy and sanitation violations (e.g., a bathroom opening directly into a living room) and repairs them dynamically by injecting buffer corridors.
- **Dynamic Door & Window Generation**: Automatically calculates exposed exterior walls and places mathematically centered windows and entrance/exit doors without overlapping. Internal passage doors are intelligently placed where rooms touch.
- **High-Quality Export Formats**: View your floor plan instantly in the browser as an interactive SVG, or export it to a standard architectural DXF file for CAD software integration.
- **Interactive UI**: Adjust zoning parameters with real-time sliders and get instant compliance assessment feedback regarding setbacks, plot coverage, and sanitation rules.

##  Tech Stack

- **Backend:** Python 3.12, FastAPI, Google GenAI SDK
- **Frontend:** React (Vite), Tailwind CSS, Framer Motion
- **Layout Rendering:** Custom Python SVG & DXF Engine
- **Deployment:** Vercel (Frontend & Serverless Functions)

##  Setup Instructions

### 1. Backend Setup

1. Open a terminal and navigate to the `backend/` directory.
2. Ensure you have Python 3.12+ installed.
3. Activate the virtual environment:
   ```bash
   .\venv\Scripts\activate
   ```
4. Install dependencies (if not already installed):
   ```bash
   pip install -r requirements.txt
   ```
5. Set your Gemini API Key as an environment variable:
   ```bash
   $env:GEMINI_API_KEY="your_api_key_here"
   ```
6. Start the FastAPI server:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   *The API will be available at http://localhost:8000*

### 2. Frontend Setup

1. Open a new terminal and navigate to the `frontend/` directory.
2. Install dependencies (if not already installed):
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
4. Open the URL provided in the terminal (usually http://localhost:5173) in your browser.

##  Deployment (Vercel)

This project is configured to be deployed as a full-stack application on Vercel. 

1. Install the Vercel CLI: `npm i -g vercel`
2. From the root directory, run:
   ```bash
   vercel --prod
   ```
3. Ensure you add the `GEMINI_API_KEY` to your Vercel project environment variables in the Vercel Dashboard for the generative AI features to function in production.
