let nativeRequestController=null,nativeRequestVersion=0;
const apiBase = window.RUNTIME_API_BASE;
const loginForm = document.querySelector("#login-form");
const advisoryForm = document.querySelector("#advisory-form");
const logoutButton = document.querySelector("#logout");
const identity = document.querySelector("#identity");
const statusLine = document.querySelector("#status");
const result = document.querySelector("#result");
const demoCredentialsButton = document.querySelector("#demo-credentials");
const historyList = document.querySelector("#history-list");
const historyEmpty = document.querySelector("#history-empty");
const historyDetail = document.querySelector("#history-detail");

function setAdvisoryBusy(busy) { advisoryForm.querySelector('button[type="submit"]').disabled=busy;for(const button of document.querySelectorAll('[data-layout-preset]'))button.disabled=busy; }
 function token() {
  return sessionStorage.getItem("stackRuntimeToken");
}

function setIdentity(user) {
  identity.textContent = `Signed in as ${user.email}`;
  identity.hidden = false;
  loginForm.hidden = true;
  logoutButton.hidden = false;
  statusLine.textContent = "Ready for a de-identified layout description.";
  loadHistory();
}

function clearIdentity(message = "Sign in to begin.") {
  nativeRequestVersion++;nativeRequestController?.abort();setAdvisoryBusy(false);
  sessionStorage.removeItem("stackRuntimeToken");
  identity.hidden = true;
  loginForm.hidden = false;
  logoutButton.hidden = true;
  result.hidden = true;
  historyDetail.hidden = true;
  historyList.replaceChildren();
  historyEmpty.textContent = "Sign in to view your saved advisories.";
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

async function loadHistory() {
  try {
    const body = await api("/api/ai/interactions");
    if (!token()) return;
    historyList.replaceChildren();
    historyEmpty.textContent = body.interactions.length ? "" : "No saved advisories yet.";
    for (const record of body.interactions) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${new Date(record.created_at * 1000).toLocaleString()} · ${record.prompt}`;
      button.addEventListener("click", () => showSavedInteraction(record.id));
      item.append(button);
      historyList.append(item);
    }
  } catch (error) {
    if (token()) historyEmpty.textContent = "Saved advisories could not be loaded.";
  }
}

async function showSavedInteraction(id) {
  try {
    const body = await api(`/api/ai/interactions/${id}`);
    if (!token()) return;
    document.querySelector("#history-advisory").innerHTML = window.BrowserAIReport.render(body.interaction.response);
    document.querySelector("#history-receipt").textContent =
      `Saved interaction ${body.interaction.id} · ${body.interaction.model}`;
    historyDetail.hidden = false;
  } catch (error) {
    historyEmpty.textContent = "This saved advisory could not be loaded.";
  }
}

demoCredentialsButton.addEventListener("click", async () => {
  try {
    const credentials = await api("/api/auth/demo-credentials");
    loginForm.elements.email.value = credentials.email;
    loginForm.elements.password.value = credentials.password;
    loginForm.requestSubmit();
  } catch (error) {
    statusLine.textContent = "Demo credentials are unavailable.";
  }
});

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
  setAdvisoryBusy(true);nativeRequestController?.abort();nativeRequestController=new AbortController();const nativeVersion=++nativeRequestVersion;
  try {
    const body = await api("/api/ai/stack-layout-advisory", {
      method: "POST",
      body: JSON.stringify({ layoutDescription: fields.get("layoutDescription") }),signal:nativeRequestController.signal,
    });
    if(nativeVersion!==nativeRequestVersion)return;
    document.querySelector("#advisory").innerHTML = window.BrowserAIReport.render(body.advisory);
    document.querySelector("#receipt").textContent =
      `Durable interaction ${body.interactionId} · Provider receipt ${body.providerReceipt.requestId}`;
    result.hidden = false;
    statusLine.textContent = "Advisory received and durably recorded.";
    loadHistory();
  } catch (error) {
    if(nativeVersion!==nativeRequestVersion)return;
    if(error.name==='AbortError'){statusLine.textContent='Request canceled.';return;}
    if (error.message === "authentication_required") clearIdentity("Your session expired. Sign in again.");
    else statusLine.textContent = "The provider is unavailable; no interaction was recorded.";
  } finally { if(nativeVersion===nativeRequestVersion)setAdvisoryBusy(false); }
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

for(const [index,button]of [...document.querySelectorAll('[data-layout-preset]')].entries())button.addEventListener('click',()=>{advisoryForm.elements.layoutDescription.value=['Illustrative vertical UIStackView with a multiline heading, flexible spacer and two equal-width actions. Explain clipping at large text sizes, evidence gaps and three next checks.','Illustrative horizontal layout with three intrinsic-size controls inside a scrolling view. Compare alignment, spacing and accessible alternatives before changing the native screen.','Illustrative nested stack layout supporting portrait and landscape. Review compression and hugging priorities, VoiceOver reading order and Dynamic Type; explain uncertain assumptions.'][index];});
document.querySelector('#cancel-advisory').addEventListener('click',()=>{nativeRequestVersion++;nativeRequestController?.abort();setAdvisoryBusy(false);statusLine.textContent='Request canceled.';});window.addEventListener('beforeunload',()=>nativeRequestController?.abort());
