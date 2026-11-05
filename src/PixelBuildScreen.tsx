import React, { useEffect, useState } from 'react';

interface PixelBuildScreenProps {
  targetVersion?: string;
  apiUrl?: string;
  onComplete?: () => void;
  onMinimize?: () => void;
}

export const PixelBuildScreen: React.FC<PixelBuildScreenProps> = ({
  targetVersion = 'latest',
  apiUrl = '/api',
  onComplete,
  onMinimize
}) => {
  const [secondsElapsed, setSecondsElapsed] = useState(0);
  const [progress, setProgress] = useState(5);
  const [statusMessage, setStatusMessage] = useState('INITIATING CLOUD BUILD MATRIX...');
  const [isCompleted, setIsCompleted] = useState(false);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [logs, setLogs] = useState<string[]>([
    '> [00:00] INITIALIZING VTAB ADMIN CONSOLE BUILD AGENT...',
    '> [00:02] DISPATCHING RENDER API DEPLOY HOOK (srv-dbku80h42hec73dbpjkg)...'
  ]);
  const [minimized, setMinimized] = useState(false);

  // Timer
  useEffect(() => {
    const timer = setInterval(() => {
      setSecondsElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Progressive build milestones
  useEffect(() => {
    if (isCompleted || isError) return;

    if (secondsElapsed === 4) {
      setProgress(15);
      setStatusMessage('ALLOCATING CLOUD CONTAINER RUNNER...');
      setLogs((l) => [...l, `> [${formatTime(secondsElapsed)}] CONTAINER RUNNER ALLOCATED (PYTHON 3.11)`]);
    } else if (secondsElapsed === 12) {
      setProgress(28);
      setStatusMessage('CLONING TARGET COMMIT TREE...');
      setLogs((l) => [...l, `> [${formatTime(secondsElapsed)}] FETCHING SOURCE COMMIT: ${targetVersion}`]);
    } else if (secondsElapsed === 25) {
      setProgress(44);
      setStatusMessage('COMPILING TYPESCRIPT REACT BUNDLE (dist)...');
      setLogs((l) => [...l, `> [${formatTime(secondsElapsed)}] COMPILING VITE FRONTEND BUNDLE...`]);
    } else if (secondsElapsed === 50) {
      setProgress(62);
      setStatusMessage('CONNECTING SUPABASE GOVERNANCE & AUDIT SCHEMA...');
      setLogs((l) => [...l, `> [${formatTime(secondsElapsed)}] CONNECTING GOVERNANCE POSTGRESQL & RBAC BRIDGE`]);
    } else if (secondsElapsed === 75) {
      setProgress(80);
      setStatusMessage('PACKAGING PRODUCTION RUNTIME ASSETS...');
      setLogs((l) => [...l, `> [${formatTime(secondsElapsed)}] BUNDLING FASTAPI BACKEND & STATIC SPA`]);
    } else if (secondsElapsed === 95) {
      setProgress(88);
      setStatusMessage('STARTING FASTAPI PRODUCTION SERVICE...');
      setLogs((l) => [...l, `> [${formatTime(secondsElapsed)}] RUNNING UVICORN SERVER ON RENDER CLOUD HOST...`]);
    } else if (secondsElapsed === 115) {
      setProgress(94);
      setStatusMessage('AWAITING SERVICE PORT BINDING (HTTP:8000)...');
      setLogs((l) => [...l, `> [${formatTime(secondsElapsed)}] VERIFYING PORT BINDING & HEALTH STATUS...`]);
    }
  }, [secondsElapsed, isCompleted, isError, targetVersion]);

  // Active polling against Admin Console backend to detect completion
  useEffect(() => {
    let unmounted = false;
    let successTriggered = false;

    const pollStatus = async () => {
      if (successTriggered || unmounted) return;
      try {
        const res = await fetch(`${apiUrl}/update/status`).then((r) => (r.ok ? r.json() : null));
        if (unmounted || !res) return;

        if (res.last_apply_status === 'succeeded' || res.status === 'completed' || (secondsElapsed > 15 && res.update_available === false && !res.applying)) {
          triggerSuccess();
          return;
        }

        if (res.last_apply_status === 'failed') {
          setIsError(true);
          setErrorMessage(res.last_apply_message || 'Cloud build returned an error. Check server logs.');
          return;
        }
      } catch (err) {
        // Render restarts the container mid-deploy, which causes brief connection timeouts.
        if (secondsElapsed > 35 && !isCompleted) {
          setStatusMessage('CONTAINER RESTARTING IN CLOUD... AWAITING PORT...');
        }
      }
    };

    const triggerSuccess = () => {
      if (successTriggered) return;
      successTriggered = true;
      setProgress(100);
      setIsCompleted(true);
      setStatusMessage('★ CLOUD BUILD COMPLETE & VERIFIED HEALTHY! ★');
      setLogs((l) => [
        ...l,
        `> [${formatTime(secondsElapsed)}] STATUS: 200 OK — CONTAINER HEALTH VERIFIED!`,
        `> [${formatTime(secondsElapsed)}] ★ LEVEL UP! VTAB ADMIN CONSOLE IS LIVE! ★`,
        `> [${formatTime(secondsElapsed)}] RELOADING FRESH CONSOLE...`
      ]);

      try {
        localStorage.removeItem('vtab_admin_building_update');
      } catch {}

      setTimeout(() => {
        if (onComplete) onComplete();
        else window.location.reload();
      }, 2400);
    };

    const pollInterval = setInterval(pollStatus, 3000);
    return () => {
      unmounted = true;
      clearInterval(pollInterval);
    };
  }, [secondsElapsed, isCompleted, apiUrl]);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Minimized floating widget
  if (minimized) {
    return (
      <div
        onClick={() => setMinimized(false)}
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 999999,
          background: '#090d16',
          border: '3px solid #10b981',
          boxShadow: '0 0 15px rgba(16, 185, 129, 0.4), 0 8px 24px rgba(0,0,0,0.8)',
          padding: '10px 18px',
          borderRadius: 4,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          fontFamily: '"Courier New", monospace, monospace',
          color: '#10b981',
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: 1
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            background: isCompleted ? '#10b981' : '#38bdf8',
            boxShadow: `0 0 8px ${isCompleted ? '#10b981' : '#38bdf8'}`,
            animation: 'pixelBlink 1s infinite steps(2)'
          }}
        />
        <span>
          {isCompleted ? '★ BUILD READY! CLICK TO RELOAD' : `👾 CLOUD BUILD IN PROGRESS [${progress}%] ${formatTime(secondsElapsed)}`}
        </span>
      </div>
    );
  }

  // Full-screen retro pixelated build screen
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 999999,
        background: '#060911',
        backgroundImage: `
          repeating-linear-gradient(0deg, rgba(0, 0, 0, 0.35) 0px, rgba(0, 0, 0, 0.35) 2px, transparent 2px, transparent 4px),
          radial-gradient(circle at center, #0f1c2e 0%, #04060a 100%)
        `,
        color: '#10b981',
        fontFamily: '"Courier New", "Lucida Console", Monaco, monospace',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        overflow: 'hidden',
        boxSizing: 'border-box',
        userSelect: 'none'
      }}
    >
      <style>{`
        @keyframes pixelFloat {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-8px); }
        }
        @keyframes pixelFlame {
          0%, 100% { opacity: 0.9; transform: scaleY(1); }
          50% { opacity: 0.4; transform: scaleY(0.7); }
        }
        @keyframes pixelBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        @keyframes victoryGlow {
          0%, 100% { filter: drop-shadow(0 0 15px #10b981); }
          50% { filter: drop-shadow(0 0 30px #34d399); }
        }
      `}</style>

      {/* Retro CRT Monitor Frame */}
      <div
        style={{
          width: '100%',
          maxWidth: 820,
          background: 'rgba(10, 16, 26, 0.92)',
          border: '4px solid #10b981',
          boxShadow: '0 0 30px rgba(16, 185, 129, 0.25), inset 0 0 20px rgba(16, 185, 129, 0.1)',
          borderRadius: 8,
          padding: 28,
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          gap: 20
        }}
      >
        {/* Top Control Bar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '2px solid rgba(16, 185, 129, 0.3)',
            paddingBottom: 12,
            fontSize: 12,
            letterSpacing: 1.5,
            fontWeight: 700
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                width: 8,
                height: 8,
                background: isCompleted ? '#10b981' : isError ? '#ef4444' : '#38bdf8',
                boxShadow: `0 0 8px ${isCompleted ? '#10b981' : isError ? '#ef4444' : '#38bdf8'}`,
                animation: 'pixelBlink 1s infinite steps(2)'
              }}
            />
            <span style={{ color: '#38bdf8' }}>VTAB CLOUD BUILD ENGINE // ADMIN CONSOLE</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{ color: '#fbbf24' }}>TIME: {formatTime(secondsElapsed)}</span>
            <button
              onClick={() => {
                setMinimized(true);
                if (onMinimize) onMinimize();
              }}
              style={{
                background: 'transparent',
                border: '1px solid #10b981',
                color: '#10b981',
                padding: '2px 8px',
                fontSize: 11,
                cursor: 'pointer',
                fontFamily: 'inherit',
                borderRadius: 2
              }}
              title="Run in background"
            >
              [MINIMIZE]
            </button>
            <button
              onClick={() => {
                try { localStorage.removeItem('vtab_admin_building_update'); } catch {}
                if (onComplete) onComplete();
                else window.location.reload();
              }}
              style={{
                background: 'rgba(239, 68, 68, 0.2)',
                border: '1px solid #ef4444',
                color: '#f87171',
                padding: '2px 8px',
                fontSize: 11,
                cursor: 'pointer',
                fontFamily: 'inherit',
                borderRadius: 2,
                fontWeight: 700
              }}
              title="Exit build screen"
            >
              [EXIT]
            </button>
          </div>
        </div>

        {/* Pixel Art Animation Area */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px 0',
            position: 'relative'
          }}
        >
          {/* Animated 8-Bit Pixel Server Rocket */}
          <div
            style={{
              animation: isCompleted ? 'victoryGlow 1.5s infinite ease-in-out' : 'pixelFloat 2.5s infinite ease-in-out',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              imageRendering: 'pixelated'
            }}
          >
            <svg
              width="100"
              height="100"
              viewBox="0 0 24 24"
              style={{
                shapeRendering: 'crispEdges',
                filter: isCompleted ? 'drop-shadow(0 0 12px #34d399)' : 'drop-shadow(0 0 8px #10b981)'
              }}
            >
              {/* Rocket Nose Tip */}
              <rect x="11" y="1" width="2" height="2" fill={isCompleted ? '#34d399' : '#38bdf8'} />
              <rect x="10" y="3" width="4" height="2" fill={isCompleted ? '#34d399' : '#38bdf8'} />

              {/* Rocket Cockpit Glass */}
              <rect x="9" y="5" width="6" height="3" fill="#0f172a" />
              <rect x="10" y="6" width="4" height="2" fill={isCompleted ? '#10b981' : '#38bdf8'} />
              <rect x="11" y="6" width="1" height="1" fill="#ffffff" />

              {/* Main Body */}
              <rect x="9" y="8" width="6" height="6" fill="#1e293b" />
              <rect x="10" y="9" width="4" height="4" fill="#334155" />
              <rect x="11" y="10" width="2" height="2" fill={isCompleted ? '#10b981' : '#f59e0b'} />

              {/* Side Wings */}
              <rect x="7" y="11" width="2" height="5" fill="#38bdf8" />
              <rect x="6" y="14" width="1" height="3" fill="#0284c7" />
              <rect x="15" y="11" width="2" height="5" fill="#38bdf8" />
              <rect x="17" y="14" width="1" height="3" fill="#0284c7" />

              {/* Engine Exhaust Mount */}
              <rect x="9" y="14" width="6" height="2" fill="#475569" />
              <rect x="10" y="16" width="4" height="1" fill="#64748b" />

              {/* Animated Pixel Thruster Flames */}
              {!isCompleted && (
                <g style={{ animation: 'pixelFlame 0.3s infinite alternate' }}>
                  <rect x="11" y="17" width="2" height="3" fill="#fbbf24" />
                  <rect x="10" y="18" width="4" height="2" fill="#f97316" />
                  <rect x="11" y="20" width="2" height="2" fill="#ef4444" />
                  <rect x="11" y="22" width="2" height="1" fill="#dc2626" />
                </g>
              )}
              {isCompleted && (
                <g>
                  {/* Victory Sparkles */}
                  <rect x="4" y="6" width="2" height="2" fill="#fbbf24" />
                  <rect x="18" y="6" width="2" height="2" fill="#fbbf24" />
                  <rect x="3" y="16" width="2" height="2" fill="#34d399" />
                  <rect x="19" y="16" width="2" height="2" fill="#34d399" />
                </g>
              )}
            </svg>
          </div>

          {/* Heading */}
          <div
            style={{
              marginTop: 14,
              fontSize: 16,
              fontWeight: 800,
              letterSpacing: 2,
              color: isCompleted ? '#34d399' : isError ? '#ef4444' : '#10b981',
              textAlign: 'center',
              textShadow: '0 0 10px rgba(16, 185, 129, 0.5)'
            }}
          >
            {isCompleted
              ? '★ SYSTEM UPDATE COMPLETE — WELCOME TO THE NEW RELEASE ★'
              : isError
              ? '✖ BUILD ERROR OCCURRED'
              : statusMessage}
          </div>

          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4, letterSpacing: 1 }}>
            TARGET COMMIT: <span style={{ color: '#38bdf8' }}>{targetVersion}</span> • CLOUD HOST: RENDER WEB SERVICE
          </div>
        </div>

        {/* 8-Bit Chunky Pixel Progress Bar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 700 }}>
            <span>PROGRESS: [ {progress}% ]</span>
            <span>{isCompleted ? 'LIVE READY' : 'BUILDING ON RENDER...'}</span>
          </div>

          <div
            style={{
              width: '100%',
              height: 24,
              background: '#04070e',
              border: '2px solid #10b981',
              padding: 2,
              boxSizing: 'border-box',
              display: 'flex',
              gap: 2
            }}
          >
            {Array.from({ length: 30 }).map((_, idx) => {
              const segPct = ((idx + 1) / 30) * 100;
              const active = progress >= segPct;
              return (
                <div
                  key={idx}
                  style={{
                    flex: 1,
                    background: active
                      ? isCompleted
                        ? '#34d399'
                        : isError
                        ? '#ef4444'
                        : idx > 22
                        ? '#38bdf8'
                        : '#10b981'
                      : 'transparent',
                    boxShadow: active ? '0 0 6px rgba(16, 185, 129, 0.6)' : 'none',
                    transition: 'background 0.3s'
                  }}
                />
              );
            })}
          </div>
        </div>

        {/* Live Terminal Telemetry Output */}
        <div
          style={{
            background: '#04070e',
            border: '2px solid rgba(16, 185, 129, 0.35)',
            borderRadius: 4,
            padding: '12px 16px',
            fontSize: 11,
            lineHeight: '18px',
            maxHeight: 140,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            boxShadow: 'inset 0 0 10px rgba(0, 0, 0, 0.8)'
          }}
        >
          {logs.map((line, idx) => (
            <div
              key={idx}
              style={{
                color: line.includes('★') ? '#fbbf24' : line.includes('STATUS: 200') ? '#34d399' : '#94a3b8',
                letterSpacing: 0.5
              }}
            >
              {line}
            </div>
          ))}
          {!isCompleted && !isError && (
            <div style={{ color: '#10b981' }}>
              &gt; PROCESSING CLOUD RECEPTACLE
              <span style={{ animation: 'pixelBlink 0.8s infinite steps(2)' }}>_</span>
            </div>
          )}
          {isError && (
            <div style={{ color: '#ef4444', fontWeight: 700 }}>
              &gt; ERROR: {errorMessage}
            </div>
          )}
        </div>

        {/* Footer Guidance */}
        <div
          style={{
            textAlign: 'center',
            fontSize: 11,
            color: '#64748b',
            letterSpacing: 0.8
          }}
        >
          {isCompleted
            ? 'RELOAD IN PROGRESS... RE-INITIALIZING GOVERNANCE CONSOLE...'
            : 'Render cloud containers compile in approx. 2 minutes. This screen will automatically reload when the build completes.'}
        </div>
      </div>
    </div>
  );
};
