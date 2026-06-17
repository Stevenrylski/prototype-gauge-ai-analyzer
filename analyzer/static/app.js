"use strict";

// Holt den Report und baut die Fehlerliste auf.
async function loadReport() {
    const summaryEl = document.getElementById("summary");
    const messageEl = document.getElementById("message");
    const listEl = document.getElementById("failures");

    try {
        const response = await fetch("/api/report");
        const data = await response.json();

        if (!response.ok) {
            showMessage(data.error || "Report konnte nicht geladen werden.");
            summaryEl.textContent = "";
            return;
        }

        renderSummary(summaryEl, data.summary);

        if (data.groups.length === 0) {
            listEl.innerHTML =
                '<li class="failure empty">Keine Fehlschlaege im Report &ndash; alles gruen.</li>';
            return;
        }

        data.groups.forEach((group) => listEl.appendChild(renderFailure(group)));
    } catch (err) {
        showMessage("Backend nicht erreichbar: " + err.message);
        summaryEl.textContent = "";
    }
}

function renderSummary(el, summary) {
    el.textContent =
        summary.projectName +
        " – Lauf: " + summary.timestamp +
        " – Status: " + summary.executionStatus +
        " (" + summary.successRate + "% erfolgreich) – " +
        summary.failureGroupCount + " Fehlergruppe(n), " +
        summary.totalFailures + " Fehlschlag/Fehlschlaege gesamt.";
}

function showMessage(text) {
    const messageEl = document.getElementById("message");
    messageEl.textContent = text;
    messageEl.hidden = false;
}

// Baut einen Listeneintrag aus der <template>-Vorlage.
function renderFailure(group) {
    const template = document.getElementById("failure-template");
    const node = template.content.cloneNode(true);

    node.querySelector(".badge").textContent =
        group.kind === "hook" ? "Hook" : "Schritt";
    node.querySelector(".step").textContent = group.step;
    node.querySelector(".error").textContent =
        group.errorMessage || "(keine Fehlermeldung)";

    const places = group.occurrences
        .map((o) => o.scenario ? o.spec + " › " + o.scenario : o.spec)
        .join(", ");
    node.querySelector(".occurrences").textContent =
        group.count > 1
            ? group.count + "× aufgetreten: " + places
            : "Aufgetreten in: " + places;

    const btn = node.querySelector(".analyze-btn");
    const analysisBox = node.querySelector(".analysis");
    const analysisText = node.querySelector(".analysis-text");
    const sentBox = node.querySelector(".sent");
    const sentText = node.querySelector(".sent-text");

    btn.addEventListener("click", () =>
        analyze(group.id, btn, analysisBox, analysisText, sentBox, sentText)
    );

    return node;
}

// Schickt einen Fehler an die KI und zeigt das Ergebnis an.
async function analyze(id, btn, analysisBox, analysisText, sentBox, sentText) {
    btn.disabled = true;
    btn.textContent = "Analysiere …";
    analysisBox.hidden = false;
    analysisText.classList.remove("error-text");
    analysisText.textContent = "Bitte warten …";
    sentBox.hidden = true;

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: id }),
        });
        const data = await response.json();

        if (!response.ok) {
            analysisText.classList.add("error-text");
            analysisText.textContent =
                "KI-Analyse fehlgeschlagen: " + (data.error || "Unbekannter Fehler.");
            btn.disabled = false;
            btn.textContent = "Erneut versuchen";
            return;
        }

        analysisText.textContent = data.analysis;
        sentText.textContent = data.sentToAI;
        sentBox.hidden = false;
        btn.textContent = "Erneut analysieren";
        btn.disabled = false;
    } catch (err) {
        analysisText.classList.add("error-text");
        analysisText.textContent = "Backend nicht erreichbar: " + err.message;
        btn.disabled = false;
        btn.textContent = "Erneut versuchen";
    }
}

document.addEventListener("DOMContentLoaded", loadReport);
