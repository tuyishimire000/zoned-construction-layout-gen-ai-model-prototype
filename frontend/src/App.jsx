import React, { useState, useEffect } from 'react';
import './index.css';

function App() {
  const [description, setDescription] = useState("I own a 600 sqm residential plot in Gasabo and want to build a three-story house with parking for two vehicles.");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  
  // Interactive state
  const [interactiveParams, setInteractiveParams] = useState(null);

  // Analyze natural language
  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('http://localhost:8000/api/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ description }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to analyze project');
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
        // Re-construct a pseudo-description to force backend to use these params
        const r = interactiveParams.rooms || {};
        const roomDesc = `${r.bedrooms || 0} bedrooms, ${r.bathrooms || 0} bathrooms, ${r.kitchens || 0} kitchens, ${r.living_rooms || 0} living rooms, ${r.offices || 0} offices.`;
        const fakeDesc = `${interactiveParams.plot_size} sqm ${interactiveParams.usage} plot with ${interactiveParams.floors} floors and parking for ${interactiveParams.parking_spaces}. ${roomDesc}`;
        
        const response = await fetch('http://localhost:8000/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: fakeDesc }),
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
        <p>AI-powered compliance checking and floor plan generation</p>
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

          {interactiveParams && (
            <div className="interactive-controls">
              <h3>Interactive Refinement</h3>
              <div className="control-grid">
                <div className="input-group">
                  <label>Plot Size (sqm): {interactiveParams.plot_size}</label>
                  <input 
                    type="range" 
                    min="100" max="5000" step="50"
                    value={interactiveParams.plot_size || 500}
                    onChange={(e) => handleParamChange('plot_size', e.target.value)}
                  />
                </div>
                <div className="input-group">
                  <label>Floors: {interactiveParams.floors}</label>
                  <input 
                    type="range" 
                    min="1" max="15" step="1"
                    value={interactiveParams.floors || 1}
                    onChange={(e) => handleParamChange('floors', e.target.value)}
                  />
                </div>
                <div className="input-group">
                  <label>Parking Spaces: {interactiveParams.parking_spaces}</label>
                  <input 
                    type="range" 
                    min="0" max="50" step="1"
                    value={interactiveParams.parking_spaces || 0}
                    onChange={(e) => handleParamChange('parking_spaces', e.target.value)}
                  />
                </div>
                <div className="input-group">
                  <label>Usage Type</label>
                  <select 
                    value={interactiveParams.usage || 'residential'}
                    onChange={(e) => handleParamChange('usage', e.target.value)}
                  >
                    <option value="residential">Residential</option>
                    <option value="commercial">Commercial</option>
                    <option value="industrial">Industrial</option>
                  </select>
                </div>
                
                <div className="input-group">
                  <label>Bedrooms: {interactiveParams.rooms?.bedrooms || 0}</label>
                  <input type="range" min="0" max="10" step="1"
                    value={interactiveParams.rooms?.bedrooms || 0}
                    onChange={(e) => handleRoomChange('bedrooms', e.target.value)} />
                </div>
                <div className="input-group">
                  <label>Bathrooms: {interactiveParams.rooms?.bathrooms || 0}</label>
                  <input type="range" min="0" max="10" step="1"
                    value={interactiveParams.rooms?.bathrooms || 0}
                    onChange={(e) => handleRoomChange('bathrooms', e.target.value)} />
                </div>
                <div className="input-group">
                  <label>Kitchens: {interactiveParams.rooms?.kitchens || 0}</label>
                  <input type="range" min="0" max="5" step="1"
                    value={interactiveParams.rooms?.kitchens || 0}
                    onChange={(e) => handleRoomChange('kitchens', e.target.value)} />
                </div>
                <div className="input-group">
                  <label>Living Rooms: {interactiveParams.rooms?.living_rooms || 0}</label>
                  <input type="range" min="0" max="5" step="1"
                    value={interactiveParams.rooms?.living_rooms || 0}
                    onChange={(e) => handleRoomChange('living_rooms', e.target.value)} />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Panel: Results */}
        <div className="panel">
          <h2>Compliance Report</h2>
          
          {!result && !loading && (
            <p style={{ color: 'var(--text-muted)' }}>
              Enter a description and click Analyze to generate a report.
            </p>
          )}

          {loading && !result && (
            <div style={{ textAlign: 'center', padding: '2rem' }}>
              <p>Extracting parameters and evaluating rules...</p>
            </div>
          )}

          {result && (
            <>
              <div className={`status-badge ${result.compliance.compliant ? 'pass' : 'fail'}`}>
                {result.compliance.compliant ? 'COMPLIANT' : 'NON-COMPLIANT'}
              </div>

              <div className="report-section">
                <h3>Extracted Parameters</h3>
                <ul>
                  <li>Plot Size: <strong>{result.extracted_parameters.plot_size || 'N/A'} sqm</strong></li>
                  <li>Floors: <strong>{result.extracted_parameters.floors || 'N/A'}</strong></li>
                  <li>Usage: <strong>{result.extracted_parameters.usage || 'N/A'}</strong></li>
                  <li>Parking: <strong>{result.extracted_parameters.parking_spaces || 'N/A'}</strong></li>
                </ul>
              </div>

              {result.compliance.violated_regulations.length > 0 && (
                <div className="report-section">
                  <h3>Violations</h3>
                  <ul className="violations">
                    {result.compliance.violated_regulations.map((v, i) => (
                      <li key={i}>{v}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="report-section">
                <h3>Recommendations</h3>
                <ul className="recommendations">
                  {result.compliance.recommendations.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>

              <div className="report-section">
                <h3>Schematic Floor Plan</h3>
                <div className="image-container">
                  <img src={result.floor_plan_base64} alt="Floor plan" />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
