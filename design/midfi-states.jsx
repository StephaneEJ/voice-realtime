/* global React, MfAvatar, MfKbd, MfMenubar */

// 8 edge cases · each shown in the same popover frame as the main views.

function MfStateNoKey() {
  return (
    <div className="mf popover">
      <MfMenubar />
      <div className="mf-caret" />

      <div className="mf-header">
        <span className="mf-display" style={{ fontSize: 15 }}>Setup needed</span>
        <button className="mf-icn sm">⚙</button>
      </div>

      <div style={{ padding: '22px 18px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
        <div style={{
          width: 56, height: 56, borderRadius: 14,
          background: 'var(--mf-warn-soft)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 26,
        }}>🔑</div>
        <div className="mf-col" style={{ gap: 4 }}>
          <span className="mf-display" style={{ fontSize: 17 }}>Add an API key</span>
          <span className="mf-body mf-dim">You need an OpenAI <em>or</em> Gemini key to start a session.<br/>Keys are stored in the macOS keychain.</span>
        </div>
        <button className="mf-btn primary lg" style={{ marginTop: 8 }}>
          Open settings → API keys
          <span style={{ display:'flex', gap: 3, marginLeft: 6 }}>
            <MfKbd>⌘</MfKbd><MfKbd>,</MfKbd>
          </span>
        </button>
      </div>

      <div style={{ position:'absolute', bottom: 12, left: 12, right: 12 }}>
        <div className="mf-banner info">
          <span className="mf-banner-icn">ⓘ</span>
          <span>Free trial: 3 minutes/day on a shared Gemini key. <span className="mf-acc" style={{ cursor: 'pointer' }}>Try without key</span></span>
        </div>
      </div>
    </div>
  );
}

function MfStateWsDown() {
  return (
    <div className="mf popover">
      <MfMenubar />
      <div className="mf-caret" />

      <div className="mf-header">
        <div className="mf-row" style={{ gap: 8 }}>
          <MfAvatar persona="koda" size="sm" />
          <span className="mf-title" style={{ fontSize: 14 }}>Koda</span>
          <span className="mf-chip danger">disconnected</span>
        </div>
        <button className="mf-icn sm">⚙</button>
      </div>

      <div style={{ padding: 16 }}>
        <div className="mf-banner danger">
          <span className="mf-banner-icn">⚠</span>
          <div className="mf-col" style={{ gap: 3 }}>
            <span className="mf-title" style={{ fontSize: 12.5, color: 'var(--mf-danger)' }}>Backend unreachable</span>
            <span className="mf-cap" style={{ color: 'rgba(255,118,118,0.8)' }}>
              No WebSocket on <span className="mf-mono">127.0.0.1:7711</span>.
              Session paused — your audio is buffered (4.2s).
            </span>
          </div>
        </div>

        <div className="mf-col" style={{ gap: 8, marginTop: 14, textAlign: 'center', alignItems:'center' }}>
          <div className="mf-mono" style={{ color: 'var(--mf-warn)' }}>
            ◌ reconnecting…  attempt 3 / 8
          </div>
          <div className="mf-bar" style={{ width: '100%', height: 4 }}>
            <i style={{ width: '38%', background: 'var(--mf-warn)' }} />
          </div>
          <span className="mf-cap">retry in 2s · exponential backoff</span>
        </div>

        <div className="mf-divider" style={{ margin: '16px 0' }} />

        <div className="mf-col" style={{ gap: 6 }}>
          <span className="mf-label">Diagnose</span>
          <button className="mf-btn ghost block">Restart local server</button>
          <button className="mf-btn ghost block">Copy connection log</button>
        </div>

        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button className="mf-btn danger">End session</button>
        </div>
      </div>
    </div>
  );
}

function MfStateBudgetHit() {
  return (
    <div className="mf popover">
      <MfMenubar />
      <div className="mf-caret" />

      <div className="mf-header">
        <span className="mf-display" style={{ fontSize: 15 }}>Budget cap reached</span>
        <button className="mf-icn sm">⚙</button>
      </div>

      <div style={{ padding: 18 }}>
        <div style={{
          width: 56, height: 56, borderRadius: 14, margin: '0 auto 12px',
          background: 'var(--mf-warn-soft)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 26,
        }}>$</div>

        <div className="mf-col" style={{ gap: 12, textAlign: 'center' }}>
          <div className="mf-col" style={{ gap: 4 }}>
            <span className="mf-display" style={{ fontSize: 17 }}>You hit $30 this month.</span>
            <span className="mf-body mf-dim">New sessions are blocked until April 1 — or raise your cap.</span>
          </div>

          <div className="mf-card" style={{ background: 'var(--mf-bg)', textAlign: 'left' }}>
            <div className="mf-between mf-cap">
              <span>Spent · March</span>
              <span className="mf-mono mf-warn">$30.00 / $30</span>
            </div>
            <div className="mf-bar warn" style={{ marginTop: 6 }}><i style={{ width: '100%' }} /></div>
            <div className="mf-between mf-cap mf-mono" style={{ marginTop: 6 }}>
              <span>14 sessions</span><span>12 days left</span>
            </div>
          </div>
        </div>

        <div className="mf-row" style={{ gap: 8, marginTop: 14 }}>
          <button className="mf-btn ghost" style={{ flex: 1 }}>Raise to $50</button>
          <button className="mf-btn primary" style={{ flex: 1 }}>Edit cap</button>
        </div>
      </div>
    </div>
  );
}

function MfStateMicDenied() {
  return (
    <div className="mf popover">
      <MfMenubar />
      <div className="mf-caret" />

      <div className="mf-header">
        <span className="mf-display" style={{ fontSize: 15 }}>Microphone access</span>
        <button className="mf-icn sm">⚙</button>
      </div>

      <div style={{ padding: '22px 18px', textAlign: 'center', display:'flex', flexDirection:'column', alignItems:'center', gap: 12 }}>
        <div style={{
          width: 56, height: 56, borderRadius: 14,
          background: 'var(--mf-danger-soft)',
          display:'flex', alignItems:'center', justifyContent:'center',
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--mf-danger)" strokeWidth="2">
            <rect x="9" y="3" width="6" height="11" rx="3"/>
            <path d="M4 11v1a8 8 0 0 0 16 0v-1M12 20v2"/>
            <line x1="3" y1="3" x2="21" y2="21" stroke="var(--mf-danger)" strokeWidth="2"/>
          </svg>
        </div>
        <div className="mf-col" style={{ gap: 4 }}>
          <span className="mf-display" style={{ fontSize: 17 }}>Mic permission denied.</span>
          <span className="mf-body mf-dim">macOS blocked microphone access.<br/>Voice is the entire point — enable it in System Settings.</span>
        </div>
        <button className="mf-btn primary lg" style={{ marginTop: 6 }}>
          Open System Settings → Privacy
        </button>
        <span className="mf-cap">After granting, the app will prompt you to re-launch.</span>
      </div>
    </div>
  );
}

function MfStateVaultEmpty() {
  return (
    <div className="mf" style={{ padding: 18, height: '100%' }}>
      <div className="mf-between" style={{ marginBottom: 12 }}>
        <div className="mf-row" style={{ gap: 9 }}>
          <button className="mf-icn sm">‹</button>
          <MfAvatar persona="koda" size="md" />
          <span className="mf-display" style={{ fontSize: 16 }}>Koda</span>
        </div>
        <button className="mf-btn primary">Save</button>
      </div>

      <div className="mf-subtabs" style={{ marginBottom: 14 }}>
        <div className="mf-subtab">Profile</div>
        <div className="mf-subtab active">Context</div>
        <div className="mf-subtab">Skills</div>
      </div>

      <div className="mf-card" style={{ background: 'var(--mf-bg)' }}>
        <div className="mf-between">
          <span className="mf-title">Context budget</span>
          <span className="mf-mono-12 mf-mute">0% used</span>
        </div>
        <span className="mf-cap mf-mono">gemini-2.5-flash-native-audio · 500k tokens</span>
        <div className="mf-bar" style={{ marginTop: 9 }}><i style={{ width: '0%' }} /></div>
      </div>

      <div className="mf-card" style={{ marginTop: 12 }}>
        <span className="mf-title mf-warn">Static · vault pin</span>
        <div className="mf-banner warn" style={{ marginTop: 12 }}>
          <span className="mf-banner-icn">📁</span>
          <div className="mf-col" style={{ gap: 3 }}>
            <span style={{ fontWeight: 500 }}>No vault folder linked.</span>
            <span className="mf-cap" style={{ color:'rgba(255,183,77,0.8)' }}>
              Point Voice at your Obsidian vault to pin files Koda can read on every call.
            </span>
          </div>
        </div>
        <div className="mf-row" style={{ gap: 8, marginTop: 12 }}>
          <button className="mf-btn block">Link vault folder…</button>
          <button className="mf-btn ghost">Skip</button>
        </div>
      </div>

      <span className="mf-cap" style={{ display:'block', marginTop: 10, textAlign:'center' }}>
        Koda will still use the sliding terminal context (8k tokens) on launch.
      </span>
    </div>
  );
}

function MfStateUnsaved() {
  return (
    <div className="mf" style={{ padding: 0, position: 'relative' }}>
      {/* dimmed editor in background */}
      <div style={{ padding: 18, opacity: 0.4, filter: 'blur(1px)', pointerEvents: 'none' }}>
        <div className="mf-between" style={{ marginBottom: 12 }}>
          <div className="mf-row" style={{ gap: 9 }}>
            <span style={{ color: 'var(--mf-mute)' }}>‹</span>
            <MfAvatar persona="koda" size="md" />
            <span className="mf-display" style={{ fontSize: 16 }}>Koda</span>
          </div>
          <button className="mf-btn primary">Save</button>
        </div>
        <div className="mf-subtabs"><div className="mf-subtab">Profile</div><div className="mf-subtab active">Context</div><div className="mf-subtab">Skills</div></div>
        <div className="mf-card" style={{ marginTop: 14, height: 100 }} />
        <div className="mf-card" style={{ marginTop: 10, height: 80 }} />
      </div>

      {/* modal dialog */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}>
        <div className="mf-card" style={{
          background: 'var(--mf-panel)',
          padding: '20px 22px',
          maxWidth: 380, width: '100%',
          boxShadow: '0 18px 60px rgba(0,0,0,0.6)',
          border: '1px solid var(--mf-border-2)',
        }}>
          <div className="mf-col" style={{ gap: 6 }}>
            <span className="mf-display" style={{ fontSize: 16 }}>Discard changes?</span>
            <span className="mf-body mf-dim">Your edits to Koda's <em>context</em> and <em>skills</em> won't be saved.</span>
          </div>
          <div className="mf-row" style={{ gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
            <button className="mf-btn ghost">Cancel</button>
            <button className="mf-btn danger">Discard</button>
            <button className="mf-btn primary">Save &amp; close</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MfStateOnboarding() {
  return (
    <div className="mf popover">
      <MfMenubar />
      <div className="mf-caret" />

      <div className="mf-header">
        <span className="mf-display" style={{ fontSize: 15 }}>Welcome</span>
      </div>

      <div style={{ padding: '20px 18px', display:'flex', flexDirection:'column', alignItems:'center', gap: 14, textAlign:'center' }}>
        <div style={{
          width: 56, height: 56, borderRadius: 50,
          background: 'var(--mf-acc-soft)',
          border: '1.5px solid var(--mf-acc)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 26,
        }}>👋</div>

        <div className="mf-col" style={{ gap: 4 }}>
          <span className="mf-display" style={{ fontSize: 18 }}>No personas yet.</span>
          <span className="mf-body mf-dim">A persona is an identity + voice + a slice of your vault. Start with a template or build from scratch.</span>
        </div>

        <div className="mf-col" style={{ gap: 5, width: '100%', marginTop: 4 }}>
          {[
            { ico:'A', label:'Aria — daily ops',  tag:'inbox · calendar · notes', p:'aria' },
            { ico:'K', label:'Koda — code coach', tag:'repos · docs · stack',     p:'koda' },
            { ico:'M', label:'Mira — writing',    tag:'drafts · style',           p:'mira' },
          ].map(t => (
            <div key={t.label} className="mf-card hover" style={{ display:'flex', alignItems:'center', gap: 10, padding: '8px 12px', textAlign:'left' }}>
              <MfAvatar persona={t.p} size="md" />
              <div className="mf-col" style={{ gap: 1, flex:1, minWidth:0 }}>
                <span className="mf-title" style={{ fontSize: 13 }}>{t.label}</span>
                <span className="mf-cap" style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{t.tag}</span>
              </div>
              <button className="mf-btn ghost" style={{ height: 24, padding: '0 8px', fontSize: 11 }}>Add</button>
            </div>
          ))}
        </div>

        <button className="mf-btn block ghost" style={{ marginTop: 4 }}>+ Start from scratch</button>
      </div>
    </div>
  );
}

function MfStateKeyInvalid() {
  return (
    <div className="mf" style={{ padding: 18 }}>
      <div className="mf-between" style={{ marginBottom: 14 }}>
        <span className="mf-display" style={{ fontSize: 16 }}>API keys</span>
        <button className="mf-icn sm">×</button>
      </div>

      <div className="mf-col" style={{ gap: 16 }}>
        {/* OK key */}
        <div className="mf-col" style={{ gap: 6 }}>
          <div className="mf-between">
            <span className="mf-title" style={{ fontSize: 13 }}>OpenAI</span>
            <span className="mf-chip ok">✓ valid · 5ms</span>
          </div>
          <div className="mf-row" style={{ gap: 6 }}>
            <div className="mf-input mono" style={{ flex: 1 }}>sk-•••••••••••••••••••••••••••f3a2</div>
            <button className="mf-btn ghost">Test</button>
          </div>
        </div>

        {/* Invalid key */}
        <div className="mf-col" style={{ gap: 6 }}>
          <div className="mf-between">
            <span className="mf-title" style={{ fontSize: 13 }}>Gemini</span>
            <span className="mf-chip danger">✗ unauthorized · 401</span>
          </div>
          <div className="mf-row" style={{ gap: 6 }}>
            <div className="mf-input mono" style={{ flex: 1, borderColor: 'rgba(255,118,118,0.5)' }}>
              AIza•••••••••••••••••••••••aB
            </div>
            <button className="mf-btn ghost">Test</button>
          </div>
          <div className="mf-banner danger">
            <span className="mf-banner-icn">⚠</span>
            <div className="mf-col" style={{ gap: 2 }}>
              <span style={{ fontWeight: 500 }}>Key rejected by Google.</span>
              <span className="mf-cap" style={{ color:'rgba(255,118,118,0.85)' }}>
                <span className="mf-mono">401 · API_KEY_INVALID</span> · the key is revoked, expired, or restricted to another project.
              </span>
            </div>
          </div>
        </div>

        {/* Missing telegram */}
        <div className="mf-col" style={{ gap: 6 }}>
          <div className="mf-between">
            <span className="mf-title" style={{ fontSize: 13 }}>Telegram (alerts)</span>
            <span className="mf-chip warn">⚠ optional</span>
          </div>
          <div className="mf-row" style={{ gap: 6 }}>
            <div className="mf-input mono" style={{ flex: 1, color:'var(--mf-mute)' }}>not set</div>
            <button className="mf-btn ghost">Add</button>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  MfStateNoKey, MfStateWsDown, MfStateBudgetHit, MfStateMicDenied,
  MfStateVaultEmpty, MfStateUnsaved, MfStateOnboarding, MfStateKeyInvalid,
});
