import React, { useEffect, useRef, useState } from "react";
import FunnelBoard from "./components/FunnelBoard.jsx";
import { useGoogleAuth } from "./auth.js";

function SignInGate({ auth }) {
  const ref = useRef(null);
  useEffect(() => { auth.renderButton(ref.current); }, [auth.ready]);
  return (
    <div className="shell">
      <div className="signin-gate">
        <h1>Primary Care Tech Overview</h1>
        <p>Sign in with your <b>@suvera.co.uk</b> Google account to continue.</p>
        <div ref={ref} />
      </div>
    </div>
  );
}

// Single-page Primary Care Tech Overview: the whole funnel, signed-up through
// functionally live (recalling / not recalling), with drill-downs and
// slide-over practice detail. The interactive onboarding checklist lives in
// the DPA-Signed slide-over.
export default function App() {
  const auth = useGoogleAuth();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch("/data/funnel_board.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err)
    return (
      <div className="shell">
        <h1>Primary Care Tech Overview</h1>
        <p style={{ color: "var(--bad)" }}>
          Failed to load <code>funnel_board.json</code>: {err}.<br />
          Run <code>python3 pipeline/build_funnel_board.py</code>.
        </p>
      </div>
    );

  // Google SSO gate (prod only — enabled when VITE_GOOGLE_CLIENT_ID is set)
  if (auth.enabled && auth.ready && !auth.user) return <SignInGate auth={auth} />;

  return (
    <div className="shell">
      <div className="apptop">
        <h1>Primary Care Tech Overview</h1>
        {data && <span className="apptop-meta">updated {new Date(data.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span>}
        {auth.user && (
          <span className="apptop-user">{auth.user.email}
            <button className="signout" onClick={auth.signOut}>sign out</button>
          </span>
        )}
      </div>
      {!data ? (
        <div className="loading">Loading…</div>
      ) : (
        <FunnelBoard data={data} auth={auth.user} />
      )}
    </div>
  );
}
