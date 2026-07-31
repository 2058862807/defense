/*
 * Patent US 63/835,655 — James Research Systems
 * File: frontend/ssaf_detector.js
 * Claim Mapping: SSAF (Patent Claim 2)
 */

// SSAF Detector — Patent Claim 2: Sequential Score Attribution Fingerprint
// Monitors score variance across last 10 consecutive transactions.
// If all 10 scores are identical (variance == 0), flags ATTRIBUTION-BLIND mode.

const SSAF_WINDOW_SIZE = 10;
let ssafScoreWindow = [];
let ssafDetected = false;

function ssafPushScore(score) {
    ssafScoreWindow.push(score);
    if (ssafScoreWindow.length > SSAF_WINDOW_SIZE) {
        ssafScoreWindow.shift();
    }
    if (ssafScoreWindow.length === SSAF_WINDOW_SIZE) {
        const variance = computeVariance(ssafScoreWindow);
        if (variance === 0 && !ssafDetected) {
            ssafDetected = true;
            ssafLogEvent('SSAF ATTRIBUTION-BLIND MODE DETECTED');
        } else if (variance > 0 && ssafDetected) {
            ssafDetected = false;
        }
    }
}

function computeVariance(arr) {
    const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
    const sqDiff = arr.reduce((a, b) => a + (b - mean) ** 2, 0);
    return sqDiff / arr.length;
}

function ssafLogEvent(message) {
    const panel = document.getElementById('ssaf-monitor-panel');
    if (!panel) return;
    const entry = document.createElement('div');
    entry.style.cssText = 'background:var(--rbg);border:1px solid var(--rbd);border-radius:3px;padding:4px 6px;margin-bottom:4px;font-size:9px;line-height:1.4';
    const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
    entry.innerHTML = `<span style="color:var(--red);font-weight:700">⚠ ${message}</span><br><span style="color:var(--sub)">${timestamp}</span>`;
    panel.insertBefore(entry, panel.firstChild);
    // Keep max 20 entries
    while (panel.children.length > 20) {
        panel.removeChild(panel.lastChild);
    }
}

// Hook into addTransaction to monitor scores
const _origAddTx = window.addTransaction;
window.addTransaction = function(tx) {
    if (tx && tx.risk_score !== undefined) {
        ssafPushScore(tx.risk_score);
    }
    _origAddTx(tx);
};
