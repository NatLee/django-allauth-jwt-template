// The demo page: a small single-page app on top of allauth's headless API.
//
// - Sign-up, login and third-party logins use allauth's *browser* endpoints
//   (session cookie + CSRF token), as allauth recommends for web pages.
// - After any login the page swaps its session for a JWT pair
//   (POST /api/auth/jwt) and calls your API with `Authorization: Bearer`.
// - Refreshing uses allauth's own endpoint (POST /_allauth/app/v1/tokens/refresh).
//
// Every URL comes from the server (the #playground-config JSON), so nothing
// here repeats a path. All text is inserted with textContent, never as HTML.
"use strict";

const config = JSON.parse(document.getElementById("playground-config").textContent);
const api = config.endpoints;
const routes = config.routes;

// ---------------------------------------------------------------------------
// Tokens (kept for this tab only)
// ---------------------------------------------------------------------------

const tokens = {
  get access() { return sessionStorage.getItem("playground.access"); },
  get refresh() { return sessionStorage.getItem("playground.refresh"); },
  save({ access_token, refresh_token }) {
    sessionStorage.setItem("playground.access", access_token);
    // With refresh-token rotation off, allauth keeps the old refresh token.
    if (refresh_token) sessionStorage.setItem("playground.refresh", refresh_token);
    showTokens();
  },
  clear() {
    sessionStorage.removeItem("playground.access");
    sessionStorage.removeItem("playground.refresh");
    showTokens();
  },
};

function decodeJwt(token) {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part.padEnd(part.length + ((4 - (part.length % 4)) % 4), "=")));
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

// `bearer`: call with the access token and without cookies, like any API client.
// `app`: an allauth app endpoint, which uses no cookies either.
async function call(method, url, { body, bearer, app } = {}) {
  const headers = { Accept: "application/json" };
  const init = { method, headers, credentials: bearer || app ? "omit" : "same-origin" };
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  if (!bearer && !app && method !== "GET") headers["X-CSRFToken"] = csrfToken();
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    logRequest(method, url, 0, { error: String(error) });
    return { status: 0, data: null };
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    // Empty or non-JSON body.
  }
  logRequest(method, url, response.status, data);
  return { status: response.status, data };
}

function errorsOf(data) {
  const errors = (data && data.errors) || [];
  if (errors.length) return errors.map((e) => e.message).join(" ");
  return (data && data.detail) || "Something went wrong.";
}

// ---------------------------------------------------------------------------
// What allauth's ?error= codes mean (third-party redirects)
// ---------------------------------------------------------------------------

const ERRORS = {
  cancelled: "You cancelled the third-party login.",
  email_taken: "That email already has an account. Log in to it first, then link the provider from the Account card.",
  email_domain_not_allowed: "Sign-up is limited to email addresses on approved domains.",
  connected_other: "That third-party account is already linked to someone else.",
  permission_denied: "Log in first, then link the account.",
  signup_closed: "Sign-up is closed.",
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

// session: the last allauth session response (who is signed in, pending steps).
const state = { session: null, user: null, providers: [], linked: [], mode: "login" };

async function loadConfig() {
  const { data } = await call("GET", api.config);
  state.providers = (data && data.data.socialaccount && data.data.socialaccount.providers) || [];
}

async function loadSession() {
  const { status, data } = await call("GET", api.session);
  state.session = data;
  state.user = status === 200 ? data.data.user : null;
  showSession();
}

async function ensureTokens() {
  if (!state.user) return;
  const payload = tokens.access && decodeJwt(tokens.access);
  if (payload && String(payload.sub) === String(state.user.id)) return;
  const { status, data } = await call("POST", api.sessionJwt);
  if (status === 200) tokens.save(data);
}

async function loadLinked() {
  const { status, data } = await call("GET", api.providers);
  state.linked = status === 200 ? data.data : [];
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function afterLogin(response) {
  if (response.status === 200) {
    state.user = response.data.data.user;
    showSession();
    await ensureTokens();
    await home();
    return;
  }
  const pending = response.data && response.data.data && response.data.data.flows
    ? response.data.data.flows.find((f) => f.is_pending)
    : null;
  if (pending && pending.id === "verify_email") {
    notify("Check your inbox: confirm the email address to finish signing in.");
  } else {
    notify(errorsOf(response.data), "error");
  }
}

function startProvider(providerId, process) {
  // A plain form POST: the browser leaves for the provider and comes back to
  // the callback route below. allauth checks the CSRF token and the state.
  const form = document.createElement("form");
  form.method = "POST";
  form.action = api.providerRedirect;
  const fields = {
    provider: providerId,
    process,
    callback_url: routes.socialaccount_login_error,
    csrfmiddlewaretoken: csrfToken(),
  };
  for (const [name, value] of Object.entries(fields)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
}

async function logout() {
  const oldAccess = tokens.access;
  await call("DELETE", api.session);
  tokens.clear();
  state.user = null;
  showSession();
  await home();
  if (oldAccess) {
    // Show that logging out ended the token as well (stateful validation).
    const { status } = await call("GET", api.me, { bearer: oldAccess });
    notify(status === 401
      ? "Logged out. The old access token is refused now too."
      : "Logged out. The old access token still works until it expires (JWT_STATEFUL_VALIDATION is off).");
  }
}

async function refreshTokens() {
  if (!tokens.refresh) return;
  const { status, data } = await call("POST", api.refresh, { app: true, body: { refresh_token: tokens.refresh } });
  if (status === 200) {
    tokens.save(data.data);
    notify("New access token issued; the old refresh token is retired.");
  } else {
    notify("The refresh token was refused (expired, used already, or you logged out).", "error");
  }
}

async function callApi() {
  const box = document.getElementById("api-result");
  const { status, data } = await call("GET", api.me, { bearer: tokens.access });
  box.hidden = false;
  box.dataset.status = status === 200 ? "ok" : "error";
  box.textContent = `${status} ${JSON.stringify(data, null, 2)}`;
  if (status === 401) notify("The API refused the token. Try “Refresh tokens”.", "error");
}

async function unlink(account) {
  const { status, data } = await call("DELETE", api.providers, {
    body: { provider: account.provider.id, account: account.uid },
  });
  if (status === 200) {
    state.linked = data.data;
    notify(`${account.provider.name} is no longer linked.`);
    showView("signed-in");
  } else {
    notify(errorsOf(data), "error");
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

const authCard = document.getElementById("auth-card");

function notify(message, kind = "info") {
  const box = document.getElementById("notice");
  box.dataset.kind = kind;
  box.querySelector(".text").textContent = message;
  box.hidden = false;
}

function setPill(id, text, kind) {
  const pill = document.getElementById(id);
  pill.dataset.kind = kind;
  pill.querySelector(".text").textContent = text;
}

function showSession() {
  if (state.user) setPill("session-pill", `Session: ${state.user.email}`, "ok");
  else setPill("session-pill", "Session: signed out", "off");
}

function formatTime(seconds) {
  return new Date(seconds * 1000).toLocaleString();
}

function showTokens() {
  const access = tokens.access;
  const payload = access && decodeJwt(access);
  document.getElementById("token-empty").hidden = Boolean(payload);
  document.getElementById("token-view").hidden = !payload;
  if (!payload) return;
  document.getElementById("claim-sub").textContent = payload.sub;
  document.getElementById("claim-iat").textContent = formatTime(payload.iat);
  document.getElementById("claim-exp").textContent = formatTime(payload.exp);
  document.getElementById("claim-jti").textContent = payload.jti;
  paintJwt(document.getElementById("access-token"), access);
  paintJwt(document.getElementById("refresh-token"), tokens.refresh || "");
  tickTokenPill();
}

// header.payload.signature in three colours, like jwt.io.
function paintJwt(element, token) {
  element.replaceChildren();
  token.split(".").forEach((part, index) => {
    if (index) element.append(".");
    const span = document.createElement("span");
    span.className = `jwt-part-${index}`;
    span.textContent = part;
    element.append(span);
  });
}

function tickTokenPill() {
  const payload = tokens.access && decodeJwt(tokens.access);
  if (!payload) {
    setPill("token-pill", "No access token", "off");
    return;
  }
  const left = Math.round(payload.exp - Date.now() / 1000);
  if (left <= 0) {
    setPill("token-pill", "Access token expired", "error");
    return;
  }
  const minutes = Math.floor(left / 60);
  const seconds = String(left % 60).padStart(2, "0");
  setPill("token-pill", `Access token: ${minutes}:${seconds} left`, left < 60 ? "warn" : "ok");
}

function fill(templateId) {
  return document.getElementById(templateId).content.cloneNode(true);
}

function providerButtons(container, process) {
  const block = container.closest(".providers-block");
  container.replaceChildren();
  for (const provider of state.providers) {
    if (!provider.flows.includes("provider_redirect")) continue;
    const button = fill("provider-button").firstElementChild;
    button.dataset.provider = provider.id;
    button.querySelector(".provider-mark").textContent = provider.name.charAt(0);
    button.querySelector(".provider-name").textContent =
      process === "login" ? provider.name : `Link ${provider.name}`;
    button.addEventListener("click", () => startProvider(provider.id, process));
    container.append(button);
  }
  if (block) block.hidden = !container.children.length;
  return container.children.length;
}

function bindRouteLinks(root) {
  root.querySelectorAll("[data-route]").forEach((link) => {
    const target = link.dataset.route === "home" ? "/" : routes[link.dataset.route];
    link.href = target;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(target);
    });
  });
}

const VIEWS = {
  "signed-out"(root) {
    const form = root.querySelector('[data-form="credentials"]');
    const submit = form.querySelector("[data-submit]");
    const password = form.elements.password;
    const setMode = (mode) => {
      state.mode = mode;
      root.querySelectorAll("[role=tab]").forEach((tab) => {
        tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
      });
      submit.textContent = mode === "login" ? "Log in" : "Create account";
      password.autocomplete = mode === "login" ? "current-password" : "new-password";
    };
    root.querySelectorAll("[role=tab]").forEach((tab) => {
      tab.addEventListener("click", () => setMode(tab.dataset.mode));
    });
    setMode(state.mode);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const body = { email: form.elements.email.value, password: password.value };
      afterLogin(await call("POST", state.mode === "login" ? api.login : api.signup, { body }));
    });
    const count = providerButtons(root.querySelector('[data-providers="login"]'), "login");
    root.querySelector("[data-no-providers]").hidden = count > 0;
  },

  "signed-in"(root) {
    const email = state.user.email || state.user.display;
    root.querySelector("[data-email]").textContent = email;
    root.querySelector("[data-initial]").textContent = (email || "?").charAt(0).toUpperCase();
    root.querySelector("[data-verified]").textContent = `user #${state.user.id}`;
    root.querySelector('[data-action="logout"]').addEventListener("click", logout);
    const list = root.querySelector("[data-linked]");
    for (const account of state.linked) {
      const item = fill("linked-account").firstElementChild;
      item.querySelector(".provider-mark").textContent = account.provider.name.charAt(0);
      item.querySelector(".provider-name").textContent = account.provider.name;
      item.querySelector(".account-name").textContent = account.display;
      item.querySelector("button").addEventListener("click", () => unlink(account));
      list.append(item);
    }
    root.querySelector("[data-none-linked]").hidden = state.linked.length > 0;
    providerButtons(root.querySelector('[data-providers="connect"]'), "connect");
  },

  "provider-signup"(root, { sociallogin }) {
    const name = sociallogin.account.provider.name;
    root.querySelector("[data-intro]").textContent =
      `${name} did not share a usable email address. Which one should your account use?`;
    const form = root.querySelector("form");
    form.elements.email.value = sociallogin.user.email || (sociallogin.email[0] || {}).email || "";
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      afterLogin(await call("POST", api.providerSignup, { body: { email: form.elements.email.value } }));
    });
  },

  "reset-request"(root) {
    const form = root.querySelector("form");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await call("POST", api.requestPasswordReset, { body: { email: form.elements.email.value } });
      notify("If that address has an account, a reset link is on its way.");
    });
  },

  "reset-key"(root, { key }) {
    const form = root.querySelector("form");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const response = await call("POST", api.resetPassword, { body: { key, password: form.elements.password.value } });
      if (response.status === 200) {
        // ACCOUNT_LOGIN_ON_PASSWORD_RESET is on: allauth signed us in as well.
        history.replaceState(null, "", "/");
        await afterLogin(response);
        notify("Password changed.");
      } else if (response.status === 401) {
        history.replaceState(null, "", "/");
        await home();
        notify("Password changed. Log in with the new one.");
      } else {
        notify(errorsOf(response.data), "error");
      }
    });
  },

  busy(root, { message }) {
    root.querySelector("[data-message]").textContent = message;
  },
};

function showView(name, options = {}) {
  const root = fill(`view-${name}`);
  VIEWS[name](root, options);
  bindRouteLinks(root);
  authCard.replaceChildren(root);
}

async function home() {
  if (state.user) {
    await loadLinked();
    showView("signed-in");
  } else {
    showView("signed-out");
  }
}

// ---------------------------------------------------------------------------
// Routes: the paths allauth puts in emails and redirects (HEADLESS_FRONTEND_URLS)
// ---------------------------------------------------------------------------

function matchRoute(pattern, path) {
  const escaped = pattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace("\\{key\\}", "([^/]+)");
  const match = new RegExp(`^${escaped}$`).exec(path);
  return match ? { key: match[1] && decodeURIComponent(match[1]) } : null;
}

const ROUTE_HANDLERS = {
  async account_confirm_email({ key }) {
    showView("busy", { message: "Confirming your email address…" });
    const response = await call("POST", api.verifyEmail, { body: { key } });
    history.replaceState(null, "", "/");
    if (response.status === 200 || response.status === 401) {
      notify("Email address confirmed.");
      await loadSession();
      await ensureTokens();
    } else {
      notify(errorsOf(response.data), "error");
    }
    await home();
  },

  async account_reset_password_from_key({ key }) {
    showView("reset-key", { key });
  },

  async account_reset_password() {
    showView("reset-request");
  },

  async account_signup() {
    state.mode = "signup";
    history.replaceState(null, "", "/");
    await home();
  },

  // Where third-party logins come back to, with ?error=<code> on failure.
  async socialaccount_login_error() {
    const query = new URLSearchParams(location.search);
    history.replaceState(null, "", "/");
    const error = query.get("error");
    if (error) notify(ERRORS[error] || `Third-party login failed (${error}).`, "error");
    const session = state.session; // loaded on start-up, after the redirect
    const pending = session && session.data && session.data.flows
      ? session.data.flows.find((f) => f.is_pending)
      : null;
    if (pending && pending.id === "provider_signup") {
      const { data } = await call("GET", api.providerSignup);
      showView("provider-signup", { sociallogin: data.data });
      return;
    }
    await ensureTokens();
    await home();
  },
};

async function navigate(path) {
  if (path !== location.pathname) history.pushState(null, "", path);
  for (const [name, pattern] of Object.entries(routes)) {
    const match = matchRoute(pattern, location.pathname);
    if (match && ROUTE_HANDLERS[name]) return ROUTE_HANDLERS[name](match);
  }
  return home();
}

// ---------------------------------------------------------------------------
// Request log
// ---------------------------------------------------------------------------

function shorten(value) {
  return JSON.stringify(
    value,
    (key, item) => (typeof item === "string" && item.length > 48 && /token/.test(key) ? `${item.slice(0, 24)}…` : item),
    2,
  );
}

function logRequest(method, url, status, data) {
  const log = document.getElementById("log");
  const item = document.createElement("li");
  const head = document.createElement("div");
  head.className = "log-head";
  const verb = document.createElement("span");
  verb.className = "verb";
  verb.textContent = method;
  const path = document.createElement("code");
  path.textContent = url;
  const code = document.createElement("span");
  code.className = `code code-${String(status).charAt(0)}xx`;
  code.textContent = status || "network error";
  head.append(verb, path, code);
  item.append(head);
  if (data) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "response";
    const body = document.createElement("pre");
    body.textContent = shorten(data);
    details.append(summary, body);
    item.append(details);
  }
  log.prepend(item);
  while (log.children.length > 40) log.lastElementChild.remove();
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

document.getElementById("call-api").addEventListener("click", callApi);
document.getElementById("refresh").addEventListener("click", refreshTokens);
document.getElementById("clear-log").addEventListener("click", () => document.getElementById("log").replaceChildren());
document.querySelector("#notice .close").addEventListener("click", () => {
  document.getElementById("notice").hidden = true;
});
window.addEventListener("popstate", () => navigate(location.pathname));
setInterval(tickTokenPill, 1000);

(async () => {
  await loadConfig();
  await loadSession();
  if (!state.user) tokens.clear();
  await ensureTokens();
  showTokens();
  await navigate(location.pathname);
})();
