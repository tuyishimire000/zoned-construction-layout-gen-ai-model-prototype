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
    setResult(null); // Clear result so loading spinner shows again during regenerate
    setError(null);
    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ description }),
      });
      
      if (!response.ok) {
        let errorMsg = 'Failed to analyze project';
        if (response.status === 429) {
            errorMsg = "API Rate Limit Exceeded. Please contact the system administrator.";
        }
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            if (typeof errorData.detail === 'string' && errorData.detail.includes('429')) {
              errorMsg = "API Rate Limit Exceeded. Please contact the system administrator.";
            } else if (response.status !== 429) {
              errorMsg = errorData.detail;
            }
          }
        } catch (e) {}
        throw new Error(errorMsg);
      }
      
      const data = await response.json();
      setResult(data);
      setInteractiveParams(data.extracted_parameters);
    } catch (err) {
      if (err.message.includes('429') || err.message.includes('RESOURCE_EXHAUSTED')) {
         setError("API Rate Limit Exceeded. Please contact the system administrator.");
      } else {
         setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  // Debounced interactive update
  useEffect(() => {
    if (!interactiveParams) return;
    
    const timeoutId = setTimeout(async () => {
      try {
        const response = await fetch('/api/render', {
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

          {error && (
            <div style={{ color: '#d32f2f', backgroundColor: '#ffebee', padding: '1rem', borderRadius: '4px', marginTop: '1rem', border: '1px solid #f44336' }}>
              <strong>Error:</strong> {error}
            </div>
          )}

        </div>

        {/* Right Panel: Results */}
        <div className="panel">
          
          {!result && !loading && !error && (
            <p style={{ color: 'var(--text-muted)' }}>
              Enter a description and click Analyze to generate a layout.
            </p>
          )}

          {loading && (
            <div className="loading-container">
              <div className="spinner"></div>
              <p className="loading-message">{loadingMessages[loadingMsgIdx]}</p>
            </div>
          )}

          {result && !loading && (
            <>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem'}}>
                    <h3 style={{margin: 0}}>Schematic Floor Plan</h3>
                    <div style={{display: 'flex', gap: '8px'}}>
                        {result.dxf_base64 && (
                            <a href={result.dxf_base64} download="floorplan.dxf" className="btn" style={{backgroundColor: '#10b981', display: 'flex', alignItems: 'center', gap: '6px', padding: '0.5rem 1rem', fontSize: '0.9rem', textDecoration: 'none', color: 'white'}}>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                Download CAD (DXF)
                            </a>
                        )}
                        <button className="btn" onClick={handleAnalyze} disabled={loading} style={{display: 'flex', alignItems: 'center', gap: '6px', padding: '0.5rem 1rem', fontSize: '0.9rem'}}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.92-10.26l5.57 5.57"/></svg>
                            Regenerate
                        </button>
                    </div>
                </div>
                <div className="image-container">
                  <img src={result.floor_plan_base64} alt="Floor plan" />
                </div>
                <div style={{marginTop: '1rem', padding: '1rem', backgroundColor: 'rgba(59, 130, 246, 0.1)', borderRadius: '8px', color: '#1e40af', fontSize: '0.95rem'}}>
                    <strong>Not satisfied with the current design?</strong> Since our layout engine is generative, you can simply click the <strong>Regenerate</strong> button above to have the AI explore a completely new architectural arrangement using the same prompt!
                </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
