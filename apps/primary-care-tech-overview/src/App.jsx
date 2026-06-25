import React, { useEffect, useRef, useState } from "react";
import FunnelBoard from "./components/FunnelBoard.jsx";
import OnboardingHub from "./components/OnboardingHub.jsx";
import { useGoogleAuth } from "./auth.js";

const LOGO = "/assets/suvera-logo.png";

function SignInGate({ auth }) {
  const ref = useRef(null);
  useEffect(() => { auth.renderButton(ref.current); }, [auth.ready]);
  return (
    <div className="shell">
      <div className="signin-gate">
        <img className="signin-logo" src={LOGO} alt="Suvera" />
        <h1>Primary Care Tech Overview</h1>
        <p>Sign in with your <b>@suvera.co.uk</b> Google account to continue.</p>
        <div ref={ref} />
      </div>
    </div>
  );
}

const tabFromUrl = () =>
  new URLSearchParams(window.location.search).get("tab") === "onboarding" ? "onboarding" : "overview";

// Single-page Primary Care Tech Overview with two tabs (?tab=overview|onboarding):
//  • Overview — the read-only funnel analytics ("where everyone's at"); the
//    interactive onboarding checklist also lives in its DPA-Signed slide-over.
//  • Onboarding Hub — the action surface for DPA-signed-onwards practices; step
//    toggles write to Neon and flow back into the Overview's "X/9" roll-up.
export default function App() {
  const auth = useGoogleAuth();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTab] = useState(tabFromUrl);

  useEffect(() => {
    fetch("/data/funnel_board.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  // keep tab state in sync with browser back/forward
  useEffect(() => {
    const onPop = () => setTab(tabFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const selectTab = (t) => {
    setTab(t);
    const u = new URL(window.location.href);
    if (t === "overview") u.searchParams.delete("tab");
    else u.searchParams.set("tab", t);
    window.history.pushState({}, "", u.pathname + u.search + u.hash);
  };

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

  // DPA-signed-onwards cohort with an ODS code — matches what the Onboarding Hub lists.
  const cohortCount = data
    ? (data.deals || []).filter((d) => (d.stage === "dpa_signed" || d.stage === "live") && d.ods).length
    : 0;

  return (
    <div className="shell">
      <div className="apptop">
        <img className="apptop-logo" src={LOGO} alt="Suvera" />
        <h1>Primary Care Tech Overview</h1>
        {data && <span className="apptop-meta">updated {new Date(data.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span>}
        {auth.user && (
          <span className="apptop-user">{auth.user.email}
            <button className="signout" onClick={auth.signOut}>sign out</button>
          </span>
        )}
      </div>

      <nav className="tabbar">
        <button className={"tabbtn" + (tab === "overview" ? " active" : "")} onClick={() => selectTab("overview")}>
          Overview{data && <span className="tabcount">{(data.deals || []).length}</span>}
        </button>
        <button className={"tabbtn" + (tab === "onboarding" ? " active" : "")} onClick={() => selectTab("onboarding")}>
          Onboarding Hub{data && <span className="tabcount">{cohortCount}</span>}
        </button>
      </nav>

      {!data ? (
        <div className="loading">Loading…</div>
      ) : tab === "onboarding" ? (
        <OnboardingHub data={data} auth={auth.user} />
      ) : (
        <FunnelBoard data={data} auth={auth.user} />
      )}
    </div>
  );
}
