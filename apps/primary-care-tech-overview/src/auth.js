import { useEffect, useState } from "react";

// Identity comes from Cloudflare Access.
//
// Access gates the whole site to @suvera.co.uk *before* the app ever loads, so
// there is no in-app sign-in — anyone who reached the app is already an
// authenticated Suvera user. We just read *who* Access authenticated (for the
// greeting + change attribution) from its identity endpoint. The API derives
// the same identity server-side from the Access JWT, so writes are attributed
// even though the browser sends no token.
//
// In local dev there's no Access in front, so /cdn-cgi/access/get-identity
// 404s, `user` stays null, and the app runs open (the manual "who" field
// supplies changed_by) — same as before.
const DOMAIN = "suvera.co.uk";

export function useAccessIdentity() {
  const [user, setUser] = useState(null); // { email, name } | null

  useEffect(() => {
    let cancelled = false;
    fetch("/cdn-cgi/access/get-identity", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((id) => {
        if (cancelled || !id) return;
        const email = (id.email || "").toLowerCase();
        if (email.endsWith("@" + DOMAIN)) setUser({ email, name: id.name || null });
      })
      .catch(() => { /* no Access in front (local dev) — run open */ });
    return () => { cancelled = true; };
  }, []);

  // End the Access session for this app (Cloudflare clears its cookie and bounces
  // the user back to the login screen).
  const signOut = () => { window.location.href = "/cdn-cgi/access/logout"; };

  return { user, signOut };
}
