import React, { useEffect, useMemo, useRef, useState } from "react";
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

// Team-tabbed Primary Care Tech Overview.
//  Overview        — the whole funnel, signed-up → recalling (+ recall volumes)
//  Partnerships    — signed-up → DPA signed (HubSpot; read-only)
//  Onboarding      — DPA signed & onboard-ready, NOT yet live (interactive, timestamped toggles)
//  Implementation  — live: two groups — not-yet-recalling, then recalling (recall volumes; read-only)
const TABS = [
  { key: "overview", label: "Overview", stages: null }, // null = all
  { key: "partnerships", label: "Partnerships", stages: ["waitlist", "demo_booked", "demo_held", "dpa_sent", "dpa_signed"] },
  { key: "onboarding", label: "Onboarding", stages: ["dpa_signed"] },
  { key: "implementation", label: "Implementation", stages: ["live", "recalling"] },
];

function readTab() {
  const t = new URL(window.location.href).searchParams.get("tab");
  return TABS.some((x) => x.key === t) ? t : "overview";
}

export default function App() {
  const auth = useGoogleAuth();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTab] = useState(readTab);

  useEffect(() => {
    fetch("/data/funnel_board.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (tab === "overview") url.searchParams.delete("tab");
    else url.searchParams.set("tab", tab);
    window.history.replaceState({}, "", url.toString());
  }, [tab]);

  // tab counts: deals whose current stage falls in the tab's scope ("recalling" = live & recalling).
  // Implementation is ODS-based (recalls.json), so it counts both cohorts, not HubSpot deals.
  const counts = useMemo(() => {
    const out = {};
    const deals = data?.deals || [];
    for (const t of TABS) {
      if (t.key === "implementation") {
        out[t.key] = (data?.recalling_practices?.length || 0) + (data?.live_not_recalling?.length || 0);
        continue;
      }
      if (!t.stages) { out[t.key] = deals.filter((d) => d.stage !== "dropped").length; continue; }
      out[t.key] = deals.filter((d) =>
        t.stages.some((s) => (s === "recalling" ? d.stage === "live" && d.recalling : d.stage === s))
      ).length;
    }
    return out;
  }, [data]);

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
      <nav className="tabbar">
        {TABS.map((t) => (
          <button key={t.key} className={"tabbtn" + (tab === t.key ? " active" : "")} onClick={() => setTab(t.key)}>
            {t.label}{data ? <span className="tabcount">{counts[t.key] ?? 0}</span> : null}
          </button>
        ))}
      </nav>
      {!data ? (
        <div className="loading">Loading…</div>
      ) : (
        <FunnelBoard data={data} scope={tab} stages={TABS.find((t) => t.key === tab)?.stages || null} auth={auth.user} />
      )}
    </div>
  );
}
