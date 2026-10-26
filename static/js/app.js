document.addEventListener('DOMContentLoaded', () => {
    // Clock
    setInterval(updateClock, 1000);
    updateClock();

    // DOM Elements
    const btnPlayVoice = document.getElementById('btn-play-voice');
    const orbTrigger = document.getElementById('orb-trigger');
    const btnReDiagnose = document.getElementById('btn-re-diagnose');
    const btnDispatchAMO = document.getElementById('btn-dispatch-amo');
    const btnToggleDemo = document.getElementById('btn-toggle-demo');
    const audioElement = document.getElementById('briefing-audio');
    const coreOrb = document.getElementById('core-orb');
    const waveBars = document.getElementById('audio-wave-bars');
    const speechText = document.getElementById('jarvis-speech-text');

    let currentCandidate = null;

    // Initial Load
    fetchDiagnostic();

    // Event Listeners
    btnPlayVoice.addEventListener('click', toggleVoiceBriefing);
    orbTrigger.addEventListener('click', toggleVoiceBriefing);
    btnReDiagnose.addEventListener('click', fetchDiagnostic);
    btnDispatchAMO.addEventListener('click', dispatchAMOOrder);
    btnToggleDemo.addEventListener('click', toggleHoldingDemo);

    function updateClock() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
        const clockEl = document.getElementById('clock-display');
        if (clockEl) clockEl.textContent = `${timeStr} IST`;
    }

    async function fetchDiagnostic() {
        showToast("Running neural market diagnostic...", "🔄");
        speechText.textContent = "Scanning market telemetry, Nifty 50 regime, and portfolio status...";
        
        try {
            const res = await fetch('/api/diagnostic');
            const data = await res.json();
            renderDashboard(data);
            showToast("Diagnostic complete. Daily closing verdict ready.", "✅");
        } catch (err) {
            console.error("Diagnostic error:", err);
            showToast("Error connecting to neural core.", "⚠️");
        }
    }

    function renderDashboard(data) {
        const { telemetry, regime, candidate, memory } = data;

        // 1. Telemetry Bar
        document.getElementById('broker-mode').textContent = telemetry.mode;
        document.getElementById('avail-cash').textContent = `₹${telemetry.available_cash.toLocaleString('en-IN')}`;
        
        document.getElementById('nifty-display').innerHTML = `${regime.nifty_close.toLocaleString('en-IN')} <span class="${regime.nifty_change_pct >= 0 ? 'badge-green' : 'badge-red'}">${regime.nifty_change_pct}%</span>`;
        document.getElementById('vix-display').innerHTML = `${regime.india_vix} <span class="badge-green">${regime.vix_status}</span>`;

        // 2. Portfolio Sentinel (Priority 1)
        const sentinelBox = document.getElementById('sentinel-box');
        const holdingStatusText = document.getElementById('holding-status-text');

        if (telemetry.has_active_holding && telemetry.active_holding) {
            const h = telemetry.active_holding;
            sentinelBox.style.display = 'block';
            holdingStatusText.innerHTML = `<span class="badge-green">GUARDIAN ACTIVE: ${h.symbol}</span>`;
            
            document.getElementById('holding-name').textContent = `${h.name} (${h.symbol})`;
            document.getElementById('holding-pnl').textContent = `${h.pnl_pct >= 0 ? '+' : ''}${h.pnl_pct}% (₹${h.pnl})`;
            document.getElementById('holding-entry').textContent = `₹${h.buy_price}`;
            document.getElementById('holding-current').textContent = `₹${h.last_price}`;
            document.getElementById('holding-target').textContent = `₹${h.target_price}`;
            document.getElementById('holding-stop').textContent = `₹${h.stop_loss_price}`;
            
            document.getElementById('sentinel-badge').textContent = h.action_badge || 'MAINTAIN';
            document.getElementById('sentinel-rationale').textContent = h.rationale || 'Maintaining position.';
            
            speechText.textContent = `"${h.voice_directive || 'Holding remains intact.'}"`;
        } else {
            sentinelBox.style.display = 'none';
            holdingStatusText.textContent = "100% CASH ALLOCATION (NO OPEN RISK)";
        }

        // 3. Priority 2: Candidate Verdict
        if (candidate && candidate.best) {
            currentCandidate = candidate.best;
            document.getElementById('cand-symbol').textContent = currentCandidate.symbol;
            document.getElementById('cand-name').textContent = currentCandidate.name;
            document.getElementById('cand-price').textContent = `₹${currentCandidate.current_price}`;
            document.getElementById('candidate-type').textContent = currentCandidate.type === 'ETF' ? 'BENCHMARK INDEX ETF' : 'LARGE-CAP BLUE CHIP';
            document.getElementById('candidate-badge').textContent = `CONVICTION SCORE: ${currentCandidate.score}/100`;

            document.getElementById('cand-invest').textContent = `₹${currentCandidate.total_investment.toLocaleString('en-IN')}`;
            document.getElementById('cand-qty').textContent = `${currentCandidate.quantity} Shares @ ₹${currentCandidate.current_price}`;
            document.getElementById('cand-target').textContent = `₹${currentCandidate.target_price}`;
            document.getElementById('cand-profit').textContent = `Expected Gain: +₹${currentCandidate.potential_profit}`;
            document.getElementById('cand-stop').textContent = `₹${currentCandidate.stop_loss}`;
            document.getElementById('cand-risk').textContent = `Max Risk: -₹${currentCandidate.potential_risk}`;
            document.getElementById('cand-rsi').textContent = currentCandidate.rsi;

            const reasonsList = document.getElementById('cand-reasons-list');
            reasonsList.innerHTML = '';
            currentCandidate.reasons.forEach(r => {
                const li = document.createElement('li');
                li.textContent = r;
                reasonsList.appendChild(li);
            });

            if (!telemetry.has_active_holding) {
                speechText.textContent = `"Good evening, sir. You have 10,000 rupees in cash. I have detected an optimal dip in ${currentCandidate.name}. Target set to 4 percent with a 2 percent defensive stop."`;
            }
        }

        // 4. Memory & Evolution Stats ("The Child Brain")
        if (memory) {
            document.getElementById('exp-pill').textContent = `🧠 ${memory.days_of_experience} DAYS OF ACTIVE EXPERIENCE`;
            document.getElementById('mem-winrate').textContent = `${memory.win_rate}%`;
            document.getElementById('mem-counts').textContent = `${memory.wins} Wins / ${memory.losses} Losses`;
            document.getElementById('mem-evaluated').textContent = memory.total_evaluated;

            if (memory.wisdom_rules && memory.wisdom_rules.length > 0) {
                const topWisdom = memory.wisdom_rules[0];
                document.getElementById('primary-wisdom').textContent = `"${topWisdom.description} (Win Rate: ${Math.round(topWisdom.confidence_score * 100)}%)"`;
            }

            const tbody = document.getElementById('memory-table-body');
            tbody.innerHTML = '';
            (memory.recent_history || []).forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.created_date}</td>
                    <td><strong>${row.name}</strong></td>
                    <td>₹${row.trigger_price}</td>
                    <td>₹${row.target_price}</td>
                    <td><span class="${row.status === 'WIN' ? 'badge-green' : (row.status === 'LOSS' ? 'badge-red' : 'badge-gold')}">${row.status} (${row.final_return_pct >= 0 ? '+' : ''}${row.final_return_pct}%)</span></td>
                    <td>${row.lesson_learned}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    }

    async function toggleVoiceBriefing() {
        if (!audioElement.paused) {
            audioElement.pause();
            stopOrbAnimation();
            return;
        }

        showToast("Synthesizing neural voice briefing...", "🎙️");
        btnPlayVoice.innerHTML = '<span class="btn-icon">⏳</span> SYNTHESIZING...';

        try {
            const res = await fetch('/api/voice-briefing');
            const data = await res.json();
            
            if (data.audio_url) {
                audioElement.src = data.audio_url + '?t=' + new Date().getTime();
                audioElement.play();
                startOrbAnimation();
                btnPlayVoice.innerHTML = '<span class="btn-icon">⏸</span> PAUSE VOICE';

                audioElement.onended = () => {
                    stopOrbAnimation();
                    btnPlayVoice.innerHTML = '<span class="btn-icon">▶</span> LISTEN TO JARVIS';
                };
            }
        } catch (err) {
            console.error("Audio playback error:", err);
            stopOrbAnimation();
            btnPlayVoice.innerHTML = '<span class="btn-icon">▶</span> LISTEN TO JARVIS';
        }
    }

    function startOrbAnimation() {
        coreOrb.classList.add('orb-speaking');
        waveBars.classList.add('waves-active');
    }

    function stopOrbAnimation() {
        coreOrb.classList.remove('orb-speaking');
        waveBars.classList.remove('waves-active');
    }

    async function dispatchAMOOrder() {
        if (!currentCandidate) return;

        const confirmMsg = `Approve AMO Order for ${currentCandidate.quantity} units of ${currentCandidate.symbol} (Total: ₹${currentCandidate.total_investment})?`;
        if (!confirm(confirmMsg)) return;

        showToast("Transmitting AMO Order to broker...", "⚡");
        try {
            const res = await fetch('/api/dispatch-order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentCandidate)
            });
            const result = await res.json();
            
            if (result.status === 'SUCCESS') {
                showToast(`AMO ORDER PLACED! Target: ₹${currentCandidate.target_price}`, "🚀");
                fetchDiagnostic(); // Refresh view to show newly held stock
            } else {
                showToast(`Order notice: ${result.reason || 'Simulation updated'}`, "ℹ️");
                fetchDiagnostic();
            }
        } catch (err) {
            console.error("Order dispatch error:", err);
            showToast("Failed to transmit order.", "⚠️");
        }
    }

    async function toggleHoldingDemo() {
        showToast("Toggling simulation state...", "🔄");
        try {
            const res = await fetch('/api/toggle-demo', { method: 'POST' });
            const data = await res.json();
            showToast(data.message, "✅");
            fetchDiagnostic();
        } catch (err) {
            console.error("Toggle error:", err);
        }
    }

    function showToast(msg, icon = "⚡") {
        const toast = document.getElementById('toast');
        const toastMsg = document.getElementById('toast-msg');
        document.querySelector('.toast-icon').textContent = icon;
        toastMsg.textContent = msg;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3500);
    }
});
