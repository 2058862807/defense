/*
 * Patent US 63/835,655 — James Research Systems
 * File: frontend/composite_risk_fusion_detector.js
 * Claim Mapping: COMPOSITE_RISK_FUSION (Patent Claim 2)
 */

// COMPOSITE_RISK_FUSION Detector — Patent Claim 2: Sequential Score Attribution Fingerprint
// Monitors score variance across last 10 consecutive transactions.
// If all 10 scores are identical (variance == 0), flags ATTRIBUTION-BLIND mode.

const COMPOSITE_RISK_FUSION_WINDOW_SIZE = 10;
let compositeRiskFusionScoreWindow = [];
let compositeRiskFusionDetected = false;

function compositeRiskFusionPushScore(score) {
    compositeRiskFusionScoreWindow.push(score);
    if (compositeRiskFusionScoreWindow.length > COMPOSITE_RISK_FUSION_WINDOW_SIZE) {
        compositeRiskFusionScoreWindow.shift();
    }
    if (compositeRiskFusionScoreWindow.length === COMPOSITE_RISK_FUSION_WINDOW_SIZE) {
        const variance = computeVariance(compositeRiskFusionScoreWindow);
        if (variance === 0 && !compositeRiskFusionDetected) {
            compositeRiskFusionDetected = true;
            compositeRiskFusionLogEvent('COMPOSITE_RISK_FUSION ATTRIBUTION-BLIND MODE DETECTED');
        } else if (variance > 0 && compositeRiskFusionDetected) {
            compositeRiskFusionDetected = false;
        }
    }
}

function computeVariance(arr) {
    const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
    const sqDiff = arr.reduce((a, b) => a + (b - mean) ** 2, 0);
    return sqDiff / arr.length;
}

function compositeRiskFusionLogEvent(message) {
    const panel = document.getElementById('compositeRiskFusion-monitor-panel');
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
        compositeRiskFusionPushScore(tx.risk_score);
    }
    _origAddTx(tx);
};
