import { useEffect, useState } from "react";

// Google Identity Services sign-in, restricted to @suvera.co.uk.
// Enabled only when VITE_GOOGLE_CLIENT_ID is set (prod). In local dev it's
// unset → auth is disabled and the app runs open (name field for changed_by).
const CLIENT_ID = (import.meta.env && import.meta.env.VITE_GOOGLE_CLIENT_ID) || "";
const DOMAIN = "suvera.co.uk";

function decodeJwt(t) {
  try { return JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); }
  catch { return {}; }
}

export function useGoogleAuth() {
  const enabled = !!CLIENT_ID;
  const [user, setUser] = useState(null);   // { email, token, exp, name }
  const [ready, setReady] = useState(!enabled);

  useEffect(() => {
    if (!enabled) return;
    const saved = sessionStorage.getItem("pcto.gauth");
    if (saved) {
      try { const u = JSON.parse(saved); if (u.exp * 1000 > Date.now()) setUser(u); } catch { /* ignore */ }
    }
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true; s.defer = true;
    s.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: (resp) => {
          const p = decodeJwt(resp.credential);
          const email = (p.email || "").toLowerCase();
          if (p.hd === DOMAIN || email.endsWith("@" + DOMAIN)) {
            const u = { email, token: resp.credential, exp: p.exp, name: p.name };
            setUser(u);
            sessionStorage.setItem("pcto.gauth", JSON.stringify(u));
          } else {
            alert("Please sign in with your @suvera.co.uk Google account.");
          }
        },
      });
      setReady(true);
    };
    document.head.appendChild(s);
  }, [enabled]);

  const renderButton = (el) => {
    if (el && window.google) window.google.accounts.id.renderButton(el, { theme: "outline", size: "large", text: "signin_with" });
  };
  const signOut = () => { setUser(null); sessionStorage.removeItem("pcto.gauth"); window.google?.accounts.id.disableAutoSelect(); };

  return { enabled, ready, user, renderButton, signOut };
}
