const apiBase = "http://127.0.0.1:31004";
const loginForm = document.querySelector("#login-form");
const advisoryForm = document.querySelector("#advisory-form");
const logoutButton = document.querySelector("#logout");
const identity = document.querySelector("#identity");
const statusLine = document.querySelector("#status");
const result = document.querySelector("#result");

function token() {
  return sessionStorage.getItem("stackRuntimeToken");
}

function setIdentity(user) {
  identity.textContent = `Signed in as ${user.email}`;
  identity.hidden = false;
  loginForm.hidden = true;
  logoutButton.hidden = false;
  statusLine.textContent = "Ready for a de-identified layout description.";
}

function clearIdentity(message = "Sign in to begin.") {
  sessionStorage.removeItem("stackRuntimeToken");
  identity.hidden = true;
  loginForm.hidden = false;
  logoutButton.hidden = true;
  result.hidden = true;
  statusLine.textContent = message;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch(`${apiBase}${path}`, { ...options, headers });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `request_${response.status}`);
  return body;
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusLine.textContent = "Signing in…";
  const fields = new FormData(loginForm);
  try {
    const body = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: fields.get("email"), password: fields.get("password") }),
    });
    sessionStorage.setItem("stackRuntimeToken", body.token);
    loginForm.reset();
    setIdentity(body.user);
  } catch (error) {
    clearIdentity("Sign in failed. Check the supplied credentials.");
  }
});

advisoryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!token()) {
    statusLine.textContent = "Sign in before requesting an advisory.";
    return;
  }
  const fields = new FormData(advisoryForm);
  statusLine.textContent = "Requesting a live provider advisory…";
  result.hidden = true;
  try {
    const body = await api("/api/ai/stack-layout-advisory", {
      method: "POST",
      body: JSON.stringify({ layoutDescription: fields.get("layoutDescription") }),
    });
    document.querySelector("#advisory").textContent = body.advisory;
    document.querySelector("#receipt").textContent =
      `Durable interaction ${body.interactionId} · Provider receipt ${body.providerReceipt.requestId}`;
    result.hidden = false;
    statusLine.textContent = "Advisory received and durably recorded.";
  } catch (error) {
    if (error.message === "authentication_required") clearIdentity("Your session expired. Sign in again.");
    else statusLine.textContent = "The provider is unavailable; no interaction was recorded.";
  }
});

logoutButton.addEventListener("click", () => clearIdentity("Signed out."));

(async () => {
  if (!token()) return;
  try {
    const body = await api("/api/auth/me");
    setIdentity(body.user);
  } catch (error) {
    clearIdentity("Your previous session is no longer valid.");
  }
})();
