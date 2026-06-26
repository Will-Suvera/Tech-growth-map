import React, { useEffect, useRef, useState } from "react";
import FunnelBoard from "./components/FunnelBoard.jsx";
import OnboardingHub from "./components/OnboardingHub.jsx";
import { useGoogleAuth } from "./auth.js";
import { firstNameFromEmail } from "./onboarding.js";

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

  // greet the signed-in user by first name (falls back to the local "who" value in dev)
  const greetName = auth.user?.email
    ? firstNameFromEmail(auth.user.email)
    : firstNameFromEmail(typeof localStorage !== "undefined" ? localStorage.getItem("pcto.who") : null);

  return (
    <div className="su-app">
      <aside className="su-sidebar">
        <div className="su-brand"><img src={LOGO} alt="Suvera" /></div>
        {greetName && <div className="su-greeting">Hello, {greetName}</div>}
        {data && <div className="su-brand-meta">updated {new Date(data.generated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</div>}

        <nav className="su-nav">
          <button className={"su-nav-item" + (tab === "overview" ? " active" : "")} onClick={() => selectTab("overview")}>
            Overview{data && <span className="su-navcount">{(data.deals || []).length}</span>}
          </button>
          <button className={"su-nav-item" + (tab === "onboarding" ? " active" : "")} onClick={() => selectTab("onboarding")}>
            Onboarding Hub{data && <span className="su-navcount">{cohortCount}</span>}
          </button>
        </nav>

        {tab === "overview" ? (
          <>
            <div className="su-onpage">
              <div className="su-onpage-title">On this page</div>
              <a href="#kpis">Activation</a>
              <a href="#weekly">Week-by-week</a>
              <a href="#revenue">Revenue goal</a>
              <a href="#funnel">Funnel</a>
              <a href="#sources">Lead sources</a>
            </div>
            <div className="su-spacer" />
          </>
        ) : (
          /* the Onboarding Hub portals its practice list here, so there's one column */
          <div id="su-hubslot" className="su-hubslot" />
        )}
        {auth.user && (
          <div className="su-user">
            <span className="su-user-email">{auth.user.email}</span>
            <button className="su-signout" onClick={auth.signOut}>sign out</button>
          </div>
        )}
      </aside>

      <main className={"su-content" + (tab === "onboarding" ? " hub" : "")}>
        {!data ? (
          <div className="loading">Loading…</div>
        ) : tab === "onboarding" ? (
          <OnboardingHub data={data} auth={auth.user} />
        ) : (
          <FunnelBoard data={data} auth={auth.user} />
        )}
      </main>
    </div>
  );
}
