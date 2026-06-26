import React, { useState, useEffect } from 'react';
import './index.css';

function App() {
  const [description, setDescription] = useState("I own a 600 sqm residential plot in Gasabo and want to build a three-story house with parking for two vehicles.");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  
  // Loading state
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0);
  const loadingMessages = [
    "Initializing AI Architect...",
    "Analyzing natural language description...",
    "Extracting room requirements and parameters...",
    "Evaluating local zoning compliance...",
    "Generating spatial layout & rendering blueprint..."
  ];
  
  // Interactive state
  const [interactiveParams, setInteractiveParams] = useState(null);

  // Cycle loading messages
  useEffect(() => {
    if (!loading) {
      setLoadingMsgIdx(0);
      return;
    }
    
    const interval = setInterval(() => {
      setLoadingMsgIdx((prev) => (prev < loadingMessages.length - 1 ? prev + 1 : prev));
    }, 1200);
    
    return () => clearInterval(interval);
  }, [loading]);

  // Analyze natural language
  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('http://localhost:8001/api/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ description }),
      });
      
      if (!response.ok) {
        let errorMsg = 'Failed to analyze project';
        try {
          const errorData = await response.json();
          if (errorData.detail) errorMsg = errorData.detail;
        } catch (e) {}
        throw new Error(errorMsg);
      }
      
      const data = await response.json();
      setResult(data);
      setInteractiveParams(data.extracted_parameters);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Debounced interactive update
  useEffect(() => {
    if (!interactiveParams) return;
    
    const timeoutId = setTimeout(async () => {
      try {
        const response = await fetch('http://localhost:8001/api/render', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(interactiveParams),
        });
        
        if (response.ok) {
          const data = await response.json();
          setResult(data);
        }
      } catch (err) {
        console.error("Failed silent update", err);
      }
    }, 500); // 500ms debounce
    
    return () => clearTimeout(timeoutId);
  }, [interactiveParams]);

  const handleParamChange = (field, value) => {
    if (!interactiveParams) return;
    setInteractiveParams({
      ...interactiveParams,
      [field]: field === 'usage' ? value : Number(value)
    });
  };

  const handleRoomChange = (roomType, value) => {
    if (!interactiveParams) return;
    setInteractiveParams({
      ...interactiveParams,
      rooms: {
        ...(interactiveParams.rooms || {}),
        [roomType]: Number(value)
      }
    });
  };

  return (
    <div className="container">
      <header>
        <h1>Smart Building Assessor</h1>
      </header>

      <div className="layout">
        {/* Left Panel: Input & Controls */}
        <div className="panel">
          <h2>Project Description</h2>
          <div className="input-group">
            <label>Describe your project</label>
            <textarea 
              value={description} 
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. 500 sqm commercial building with 4 floors..."
            />
          </div>
          <button className="btn" onClick={handleAnalyze} disabled={loading}>
            {loading ? 'Analyzing...' : 'Analyze Project'}
          </button>

          {error && <div style={{ color: 'var(--danger)', marginTop: '1rem' }}>{error}</div>}

        </div>

        {/* Right Panel: Results */}
        <div className="panel">
          
          {!result && !loading && (
            <p style={{ color: 'var(--text-muted)' }}>
              Enter a description and click Analyze to generate a layout.
            </p>
          )}

          {loading && !result && (
            <div className="loading-container">
              <div className="spinner"></div>
              <p className="loading-message">{loadingMessages[loadingMsgIdx]}</p>
            </div>
          )}

          {result && (
            <>
                <h3>Schematic Floor Plan</h3>
                <div className="image-container">
                  <img src={result.floor_plan_base64} alt="Floor plan" />
                </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
