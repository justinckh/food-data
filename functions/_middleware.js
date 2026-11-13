// Password lock for the whole site (pages, files and API) while it is in development.
// Our own login page asks for the password only (no user name). After the correct password the
// browser keeps a cookie for 30 days. The cookie holds a hash of the password, not the password,
// so a new password logs everybody out.
//
// Secret: SITE_PASSWORD (Cloudflare Pages secret, production). If it is not set (e.g. `npm run dev`
// without it in .dev.vars), the site is open. To remove the lock: delete the secret and deploy again.

const COOKIE = "site_auth";
const MAX_AGE = 30 * 86400;
const LOGIN_PATH = "/__login";

async function tokenFor(password) {
  const data = new TextEncoder().encode(`hk-food-nutrition:${password}`);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function cookieValue(request, name) {
  const m = (request.headers.get("cookie") || "").match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return m ? m[1] : null;
}

const LOGIN_PAGE = (error) => `<!doctype html>
<html lang="zh-HK"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>請輸入密碼 - 食物營養資料庫</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #FFF8EE; color: #1B1A17;
    font-family: -apple-system, "PingFang HK", "Noto Sans TC", sans-serif; padding: 20px; }
  form { width: 100%; max-width: 360px; background: #fff; border: 1px solid #ECE7DD; border-radius: 22px;
    padding: 28px 24px; box-shadow: 0 8px 24px #0000000A; }
  .brand { display: flex; align-items: center; gap: 8px; font-weight: 900; font-size: 17px; margin-bottom: 18px; }
  .brand i { width: 10px; height: 10px; border-radius: 999px; background: #FCA104; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  p { font-size: 14px; color: #54514A; margin: 0 0 18px; line-height: 1.6; }
  input { width: 100%; height: 48px; padding: 0 16px; border-radius: 12px; border: 1.5px solid #ECE7DD;
    background: #FFF8EE; font-size: 17px; }
  input:focus { outline: none; border-color: #FCA104; background: #fff; }
  button { width: 100%; height: 48px; margin-top: 12px; border: 0; border-radius: 999px; background: #FCA104;
    color: #1B1A17; font-size: 16px; font-weight: 800; cursor: pointer; }
  button:hover { background: #E08D00; }
  .err { color: #B4540A; font-weight: 600; font-size: 14px; margin: 10px 0 0; min-height: 1.2em; }
</style></head>
<body>
<form method="post" action="${LOGIN_PATH}" id="f">
  <div class="brand"><i></i>食物營養資料庫</div>
  <h1>網站開發中</h1>
  <p>請輸入密碼瀏覽。</p>
  <input type="password" name="password" id="pw" autocomplete="current-password" autofocus aria-label="密碼" placeholder="密碼">
  <button type="submit">進入</button>
  <div class="err" id="err" role="alert">${error ? "密碼不正確，請再試。" : ""}</div>
</form>
<script>
  // log in without leaving the page, so the address (and its #/... part) stays the same
  document.getElementById("f").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = new URLSearchParams({ password: document.getElementById("pw").value });
    const r = await fetch("${LOGIN_PATH}", { method: "POST", body, headers: { "x-login": "fetch" } });
    if (r.ok) location.reload();
    else { document.getElementById("err").textContent = "密碼不正確，請再試。"; document.getElementById("pw").select(); }
  });
</script>
</body></html>`;

const html = (body, status) => new Response(body, {
  status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
});

export async function onRequest(context) {
  const { request, env } = context;
  const expected = env.SITE_PASSWORD;
  if (!expected) return context.next();
  const url = new URL(request.url);
  const token = await tokenFor(expected);

  if (url.pathname === LOGIN_PATH && request.method === "POST") {
    const form = await request.formData().catch(() => null);
    const ok = form && form.get("password") === expected;
    const viaFetch = request.headers.get("x-login") === "fetch";
    if (!ok) return viaFetch ? new Response("wrong password", { status: 401, headers: { "cache-control": "no-store" } }) : html(LOGIN_PAGE(true), 401);
    return new Response(null, {
      status: viaFetch ? 204 : 303,
      headers: {
        ...(viaFetch ? {} : { location: "/" }),
        "set-cookie": `${COOKIE}=${token}; Path=/; Max-Age=${MAX_AGE}; HttpOnly; Secure; SameSite=Lax`,
        "cache-control": "no-store",
      },
    });
  }

  if (cookieValue(request, COOKIE) === token) return context.next();

  if (url.pathname.startsWith("/api/")) {
    return new Response(JSON.stringify({ error: "password required" }), {
      status: 401, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  }
  return html(LOGIN_PAGE(false), 401);
}
