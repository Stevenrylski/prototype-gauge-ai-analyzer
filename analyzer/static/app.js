"use strict";

// Zustand: kompletter Report (alle Workspaces + Gesamtsicht) und aktiver Tab.
let reportData = null;
let activeTab = "__aggregate__";

// Gerenderte Karten des aktiven Tabs (fuer "Alle analysieren").
let renderedCards = [];
let analyzeAllRunning = false;

async function loadReport() {
    const summaryEl = document.getElementById("summary");

    try {
        const response = await fetch("/api/report");
        const data = await response.json();

        if (!response.ok) {
            showMessage(data.error || "Report konnte nicht geladen werden.");
            summaryEl.textContent = "";
            return;
        }

        reportData = data;
        renderSummary(summaryEl, data.aggregate.summary);
        renderTabs(data);
        document.getElementById("cluster-bar").hidden = false;
        renderActiveTab();
    } catch (err) {
        showMessage("Backend nicht erreichbar: " + err.message);
        summaryEl.textContent = "";
    }
}

function renderSummary(el, summary) {
    el.textContent =
        summary.loadedWorkspaceCount + " von " + summary.workspaceCount +
        " Workspaces geladen - " +
        summary.failureGroupCount + " Fehlergruppe(n), " +
        summary.totalFailures + " Fehlschlag/Fehlschlaege gesamt.";
}

function showMessage(text) {
    const messageEl = document.getElementById("message");
    messageEl.textContent = text;
    messageEl.hidden = false;
}

// ---------------------------------------------------------------------------
// Tabs: "Gesamt" + ein Tab pro Workspace.
// ---------------------------------------------------------------------------
function renderTabs(data) {
    const nav = document.getElementById("tabs");
    nav.innerHTML = "";
    nav.hidden = false;

    const tabs = [{
        key: "__aggregate__",
        label: "Gesamt (" + data.aggregate.summary.loadedWorkspaceCount + " Workspaces)",
    }];
    data.workspaces.forEach((ws) => {
        tabs.push({
            key: ws.name,
            label: ws.name + (ws.error ? " ⚠" : ""),
            error: ws.error,
        });
    });

    tabs.forEach((tab) => {
        const btn = document.createElement("button");
        btn.className = "tab" + (tab.key === activeTab ? " active" : "");
        btn.textContent = tab.label;
        if (tab.error) btn.title = tab.error;
        btn.addEventListener("click", () => {
            activeTab = tab.key;
            nav.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            renderActiveTab();
        });
        nav.appendChild(btn);
    });
}

function activeGroups() {
    if (activeTab === "__aggregate__") return reportData.aggregate.groups;
    const ws = reportData.workspaces.find((w) => w.name === activeTab);
    if (!ws) return [];
    if (ws.error) return { error: ws.error };
    return ws.groups;
}

function renderActiveTab() {
    const listEl = document.getElementById("failures");
    listEl.innerHTML = "";
    renderedCards = [];

    const groups = activeGroups();
    if (groups.error) {
        listEl.innerHTML =
            '<li class="failure empty-error">Workspace nicht ladbar: ' +
            escapeHtml(groups.error) + "</li>";
        updateAnalyzeAllBar();
        return;
    }
    if (groups.length === 0) {
        listEl.innerHTML =
            '<li class="failure empty">Keine Fehlschlaege &ndash; alles gruen.</li>';
        updateAnalyzeAllBar();
        return;
    }
    groups.forEach((group) => {
        const node = renderFailure(group);
        listEl.appendChild(node);
        renderedCards.push({ group: group, root: listEl.lastElementChild });
    });
    updateAnalyzeAllBar();
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Fehlergruppen-Karte
// ---------------------------------------------------------------------------
function renderFailure(group) {
    const template = document.getElementById("failure-template");
    const node = template.content.cloneNode(true);
    const root = node.querySelector(".failure");

    node.querySelector(".badge").textContent =
        group.kind === "hook" ? "Hook" : "Schritt";
    node.querySelector(".step").textContent = group.step;
    node.querySelector(".error").textContent =
        group.errorMessage || "(keine Fehlermeldung)";

    // "tritt in X von Y Workspaces auf" nur in der Gesamtsicht interessant.
    const wsBadge = node.querySelector(".badge-workspaces");
    const totalWs = reportData.aggregate.summary.loadedWorkspaceCount;
    if (activeTab === "__aggregate__" && group.workspaces.length > 0) {
        wsBadge.textContent = group.workspaces.length + " von " + totalWs + " Workspaces";
        wsBadge.hidden = false;
        if (group.workspaces.length > 1) wsBadge.classList.add("badge-multi");
    }

    // Cache-Hinweis: Analyse existiert bereits (aus frueherem Lauf/Neustart).
    const cachedBadge = node.querySelector(".badge-cached");
    if (group.analysisMeta) {
        cachedBadge.hidden = false;
        cachedBadge.title = "Analysiert am " + group.analysisMeta.analyzedAt +
            " (" + group.analysisMeta.backend + ")";
    }

    // Meldungs-Varianten: gleiche Fehlerart, unterschiedliche dynamische Werte.
    const variants = node.querySelector(".variants");
    if (group.variantCount > 1) {
        variants.hidden = false;
        node.querySelector(".variants-summary").textContent =
            group.variantCount + " Varianten der Meldung (gleiches Muster, " +
            "andere Werte) - Beispiele anzeigen";
        const list = node.querySelector(".variants-list");
        group.variants.forEach((variant) => {
            const li = document.createElement("li");
            li.textContent = variant;
            list.appendChild(li);
        });
    }

    node.querySelector(".occurrences").textContent = occurrencesText(group);

    // Analyse + Chat
    const btn = node.querySelector(".analyze-btn");
    const reanalyzeBtn = node.querySelector(".reanalyze-btn");
    btn.textContent = group.analysisMeta
        ? "Analyse anzeigen (gespeichert)"
        : "Mit KI analysieren";

    btn.addEventListener("click", () => analyze(group, root, false));
    reanalyzeBtn.addEventListener("click", () => analyze(group, root, true));

    const form = node.querySelector(".chat-form");
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        sendChat(group, root);
    });

    return node;
}

function occurrencesText(group) {
    const places = [];
    const seen = new Set();
    for (const occ of group.occurrences) {
        const prefix = activeTab === "__aggregate__" && occ.workspace
            ? occ.workspace + " › " : "";
        const place = prefix + (occ.scenario ? occ.spec + " › " + occ.scenario : occ.spec);
        if (!seen.has(place)) {
            seen.add(place);
            places.push(place);
        }
        if (places.length >= 6) break;
    }
    let text = group.count > 1
        ? group.count + "× aufgetreten: " + places.join(", ")
        : "Aufgetreten in: " + places.join(", ");
    const distinct = new Set(group.occurrences.map((o) =>
        (o.workspace || "") + o.spec + o.scenario)).size;
    if (distinct > places.length) {
        text += " ... und " + (distinct - places.length) + " weitere Stellen";
    }
    return text;
}

// ---------------------------------------------------------------------------
// KI-Analyse
// ---------------------------------------------------------------------------

// Rendert die vier Felder der strukturierten Analyse: Klassifikation als
// Badge, Konfidenz als Label (Warnfarbe bei "niedrig"), Ursache + Massnahme
// als Textabschnitte.
function renderAnalysis(root, analysis) {
    root.querySelector(".analysis-badges").hidden = false;
    root.querySelector(".analysis-fields").hidden = false;
    root.querySelector(".analysis-class").textContent = analysis.klassifikation;
    const confidence = root.querySelector(".analysis-confidence");
    confidence.textContent = "Konfidenz: " + analysis.konfidenz;
    confidence.classList.toggle("confidence-low", analysis.konfidenz === "niedrig");
    root.querySelector(".analysis-cause").textContent = analysis.ursache;
    root.querySelector(".analysis-action").textContent = analysis.massnahme;
}

// ---------------------------------------------------------------------------
// "Alle analysieren": jede Fehlergruppe des aktiven Tabs nacheinander
// analysieren. Sequenziell, um das Rate-Limit des KI-Anbieters nicht zu
// reissen bereits gespeicherte Analysen kommen ohne KI-Anfrage aus dem Cache.
// ---------------------------------------------------------------------------
function updateAnalyzeAllBar() {
    const bar = document.getElementById("analyze-all-bar");
    const btn = document.getElementById("analyze-all-btn");
    const status = document.getElementById("analyze-all-status");

    if (analyzeAllRunning) return; // laufende Anzeige nicht ueberschreiben

    if (renderedCards.length === 0) {
        bar.hidden = true;
        return;
    }
    bar.hidden = false;
    btn.disabled = false;
    status.textContent = "";
    const scope = activeTab === "__aggregate__" ? "alle Workspaces" : activeTab;
    btn.textContent = "Alle " + renderedCards.length +
        " Fehlergruppen mit KI analysieren (" + scope + ")";
}

async function runAnalyzeAll() {
    if (analyzeAllRunning) return;
    const cards = renderedCards.slice();
    const btn = document.getElementById("analyze-all-btn");
    const status = document.getElementById("analyze-all-status");

    analyzeAllRunning = true;
    btn.disabled = true;

    let failed = 0;
    for (let i = 0; i < cards.length; i++) {
        status.textContent = "Analysiere " + (i + 1) + " von " + cards.length + " ...";
        const ok = await analyze(cards[i].group, cards[i].root, false);
        if (!ok) failed++;
    }

    status.textContent = failed === 0
        ? "Fertig: alle " + cards.length + " Fehlergruppen analysiert."
        : "Fertig: " + (cards.length - failed) + " von " + cards.length +
          " analysiert, " + failed + " fehlgeschlagen (Details an den Karten).";
    analyzeAllRunning = false;
    btn.disabled = false;
}

async function analyze(group, root, force) {
    const btn = root.querySelector(".analyze-btn");
    const reanalyzeBtn = root.querySelector(".reanalyze-btn");
    const analysisBox = root.querySelector(".analysis");
    const analysisText = root.querySelector(".analysis-text");
    const metaEl = root.querySelector(".analysis-meta");

    btn.disabled = true;
    reanalyzeBtn.disabled = true;
    btn.textContent = "Analysiere ...";
    analysisBox.hidden = false;
    root.querySelector(".analysis-badges").hidden = true;
    root.querySelector(".analysis-fields").hidden = true;
    analysisText.hidden = false;
    analysisText.classList.remove("error-text");
    analysisText.textContent = "Bitte warten ...";

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: group.id, force: force }),
        });
        const data = await response.json();

        if (!response.ok) {
            analysisText.classList.add("error-text");
            analysisText.textContent =
                "KI-Analyse fehlgeschlagen: " + (data.error || "Unbekannter Fehler.");
            btn.disabled = false;
            reanalyzeBtn.disabled = false;
            btn.textContent = "Erneut versuchen";
            return false;
        }

        analysisText.hidden = true;
        renderAnalysis(root, data.analysis);
        root.querySelector(".sent-text").textContent = data.sentToAI;
        metaEl.textContent = data.cached
            ? "(gespeichert vom " + formatTimestamp(data.analyzedAt) + " - nicht erneut angefragt)"
            : "(neu analysiert am " + formatTimestamp(data.analyzedAt) + ", " + data.backend
              + (data.model ? " · " + data.model : "") + ")";

        btn.hidden = true;
        reanalyzeBtn.hidden = false;
        reanalyzeBtn.disabled = false;

        renderChatHistory(root, data.chat || []);
        return true;
    } catch (err) {
        analysisText.classList.add("error-text");
        analysisText.textContent = "Backend nicht erreichbar: " + err.message;
        btn.disabled = false;
        reanalyzeBtn.disabled = false;
        btn.textContent = "Erneut versuchen";
        return false;
    }
}

function formatTimestamp(iso) {
    return iso ? iso.replace("T", " ") : "unbekannt";
}

// ---------------------------------------------------------------------------
// Chat: Rueckfragen zu einem bereits analysierten Fehler
// ---------------------------------------------------------------------------
function renderChatHistory(root, chat) {
    const history = root.querySelector(".chat-history");
    history.innerHTML = "";
    chat.forEach((message) => appendChatMessage(history, message.role, message.content));
}

function appendChatMessage(history, role, content) {
    const div = document.createElement("div");
    div.className = "chat-message " + (role === "user" ? "chat-user" : "chat-assistant");
    div.textContent = content;
    history.appendChild(div);
    history.scrollTop = history.scrollHeight;
}

async function sendChat(group, root) {
    const input = root.querySelector(".chat-input");
    const sendBtn = root.querySelector(".chat-send");
    const history = root.querySelector(".chat-history");
    const message = input.value.trim();
    if (!message) return;

    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;
    appendChatMessage(history, "user", message);

    const pending = document.createElement("div");
    pending.className = "chat-message chat-assistant chat-pending";
    pending.textContent = "KI antwortet ...";
    history.appendChild(pending);
    history.scrollTop = history.scrollHeight;

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: group.id, message: message }),
        });
        const data = await response.json();
        pending.remove();

        if (!response.ok) {
            appendChatMessage(history, "assistant",
                "Fehler: " + (data.error || "Unbekannter Fehler."));
        } else {
            appendChatMessage(history, "assistant", data.reply);
        }
    } catch (err) {
        pending.remove();
        appendChatMessage(history, "assistant", "Backend nicht erreichbar: " + err.message);
    } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

// ---------------------------------------------------------------------------
// KI-Aehnlichkeits-Check: welche Gruppen sind vermutlich dieselbe Ursache?
// ---------------------------------------------------------------------------
async function runCluster(force) {
    const btn = document.getElementById("cluster-btn");
    const status = document.getElementById("cluster-status");
    const resultsEl = document.getElementById("cluster-results");

    btn.disabled = true;
    status.textContent = "KI vergleicht die Fehlergruppen ...";

    try {
        const response = await fetch("/api/cluster", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ force: force }),
        });
        const data = await response.json();

        if (!response.ok) {
            status.textContent = "Fehlgeschlagen: " + (data.error || "Unbekannter Fehler.");
            btn.disabled = false;
            return;
        }

        status.textContent = data.cached
            ? "Ergebnis gespeichert vom " + formatTimestamp(data.createdAt) + " (nicht erneut angefragt)."
            : (data.note || "Neu geprueft am " + formatTimestamp(data.createdAt) + ".");
        renderClusters(resultsEl, data.clusters || []);
        btn.textContent = "Aehnliche Ursachen erneut pruefen";
        btn.onclick = () => runCluster(true);
        btn.disabled = false;
    } catch (err) {
        status.textContent = "Backend nicht erreichbar: " + err.message;
        btn.disabled = false;
    }
}

function renderClusters(container, clusters) {
    container.innerHTML = "";
    container.hidden = false;

    if (clusters.length === 0) {
        container.innerHTML =
            '<p class="cluster-empty">Keine Gruppen mit vermutlich gleicher Ursache gefunden.</p>';
        return;
    }

    const byId = new Map(reportData.aggregate.groups.map((g) => [g.id, g]));
    clusters.forEach((cluster, index) => {
        const box = document.createElement("div");
        box.className = "cluster";

        const title = document.createElement("h3");
        title.textContent = "Vermutlich gleiche Ursache #" + (index + 1);
        box.appendChild(title);

        const list = document.createElement("ul");
        cluster.ids.forEach((id) => {
            const group = byId.get(id);
            const li = document.createElement("li");
            li.textContent = group
                ? group.step + " (" + group.count + "×)"
                : "(unbekannte Gruppe " + id + ")";
            list.appendChild(li);
        });
        box.appendChild(list);

        const reason = document.createElement("p");
        reason.className = "cluster-reason";
        reason.textContent = cluster.reason;
        box.appendChild(reason);

        container.appendChild(box);
    });
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("cluster-btn").onclick = () => runCluster(false);
    document.getElementById("analyze-all-btn").onclick = () => runAnalyzeAll();
    loadReport();
});
