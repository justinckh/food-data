// Password lock for the whole site (pages, files and API) while it is in development.
// The browser shows its own login box (HTTP Basic auth). Any user name works; only the password is checked.
//
// Secret: SITE_PASSWORD (Cloudflare Pages secret, production). If it is not set (e.g. `npm run dev`
// without it in .dev.vars), the site is open. To remove the lock: delete the secret and deploy again.

const REALM = "HK food nutrition (in development)";   // ASCII only: HTTP header value

function passwordOf(request) {
  const h = request.headers.get("authorization") || "";
  if (!h.startsWith("Basic ")) return null;
  try {
    const decoded = new TextDecoder().decode(Uint8Array.from(atob(h.slice(6)), (c) => c.charCodeAt(0)));
    return decoded.slice(decoded.indexOf(":") + 1);
  } catch {
    return null;
  }
}

export async function onRequest(context) {
  const expected = context.env.SITE_PASSWORD;
  if (!expected || passwordOf(context.request) === expected) return context.next();
  return new Response("需要密碼才可以瀏覽這個網站。", {
    status: 401,
    headers: {
      "www-authenticate": `Basic realm="${REALM}", charset="UTF-8"`,
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
