/**
 * TechFig Demo — Application Logic
 *
 * Handles: chat interface, template picker, sketch upload,
 * SVG preview, zoom controls, and download buttons.
 */

// ── Configuration ────────────────────────────────────────────────
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000'
    : 'https://techfig-api.up.railway.app';  // TODO: Update with actual Railway URL

// ── DOM Elements ─────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const chatArea = $('#chat-area');
const templateArea = $('#template-area');
const sketchArea = $('#sketch-area');
const chatInputArea = $('#chat-input-area');
const messagesEl = $('#messages');
const chatInput = $('#chat-input');
const sendBtn = $('#send-btn');
const styleSelect = $('#style-select');

const previewPlaceholder = $('#preview-placeholder');
const svgContainer = $('#svg-container');
const downloadBar = $('#download-bar');

const templateGrid = $('#template-grid');
const uploadZone = $('#upload-zone');
const sketchInput = $('#sketch-input');
const sketchPreviewImg = $('#sketch-preview-img');
const uploadPreview = $('#upload-preview');
const sketchSubmitBtn = $('#sketch-submit-btn');

// ── State ────────────────────────────────────────────────────────
let currentSvg = null;
let currentSpec = null;
let zoomLevel = 1;

// ── Mode Switching ───────────────────────────────────────────────
$$('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;

        // Toggle active button
        $$('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Show/hide areas
        chatArea.classList.toggle('hidden', mode !== 'chat');
        templateArea.classList.toggle('hidden', mode !== 'template');
        sketchArea.classList.toggle('hidden', mode !== 'sketch');
        chatInputArea.classList.toggle('hidden', mode === 'template');
    });
});

// ── Template Rendering ───────────────────────────────────────────
function renderTemplateGrid() {
    if (!window.TEMPLATES) return;

    templateGrid.innerHTML = '';
    for (const [key, tmpl] of Object.entries(window.TEMPLATES)) {
        const card = document.createElement('div');
        card.className = 'template-card';
        card.innerHTML = `
            <h3>${tmpl.name}</h3>
            <p>${tmpl.description}</p>
            <span style="font-size: 0.72rem; color: var(--accent-cyan);">${tmpl.category}</span>
        `;
        card.addEventListener('click', () => loadTemplate(key, tmpl));
        templateGrid.appendChild(card);
    }
}

async function loadTemplate(key, tmpl) {
    addMessage('user', `Load template: ${tmpl.name}`);
    addMessage('system', 'Rendering...');

    // Switch to chat view to show the message
    $$('.mode-btn').forEach(b => b.classList.remove('active'));
    $('#mode-chat-btn').classList.add('active');
    chatArea.classList.remove('hidden');
    templateArea.classList.add('hidden');
    chatInputArea.classList.remove('hidden');

    try {
        const res = await fetch(`${API_BASE}/api/reconstruct`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                spec: tmpl.spec,
                style: styleSelect.value
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'API error');
        }

        const data = await res.json();
        showSvg(data.svg);
        currentSpec = data.spec;
        removeLastMessage();
        addMessage('system', `✅ ${tmpl.name} rendered! Use the preview panel to inspect and download.`);
    } catch (e) {
        removeLastMessage();
        addMessage('system', `❌ Error: ${e.message}`);
    }
}

// ── Chat Input ───────────────────────────────────────────────────
sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';
    addMessage('user', text);
    addMessage('loading', 'Generating...');

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                current_spec: currentSpec
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'API error');
        }

        const data = await res.json();
        removeLastMessage();

        if (data.status === 'placeholder') {
            addMessage('system', `⚠️ ${data.message}`);
        } else if (data.svg) {
            showSvg(data.svg);
            currentSpec = data.spec;
            addMessage('system', '✅ Diagram generated! Check the preview panel.');
        } else {
            addMessage('system', JSON.stringify(data, null, 2));
        }
    } catch (e) {
        removeLastMessage();
        addMessage('system', `❌ Error: ${e.message}`);
    }
}

// ── Sketch Upload ────────────────────────────────────────────────
uploadZone.addEventListener('click', () => sketchInput.click());
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});
uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});
uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        handleSketchFile(e.dataTransfer.files[0]);
    }
});
sketchInput.addEventListener('change', () => {
    if (sketchInput.files.length) {
        handleSketchFile(sketchInput.files[0]);
    }
});

function handleSketchFile(file) {
    const reader = new FileReader();
    reader.onload = () => {
        sketchPreviewImg.src = reader.result;
        uploadZone.classList.add('hidden');
        uploadPreview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);

    // Store for submit
    window._sketchFile = file;
}

sketchSubmitBtn.addEventListener('click', async () => {
    if (!window._sketchFile) return;

    // Switch to chat view
    $$('.mode-btn').forEach(b => b.classList.remove('active'));
    $('#mode-chat-btn').classList.add('active');
    chatArea.classList.remove('hidden');
    sketchArea.classList.add('hidden');
    chatInputArea.classList.remove('hidden');

    addMessage('user', '📸 Uploaded sketch for reconstruction');
    addMessage('loading', 'Analyzing sketch with AI vision...');

    const formData = new FormData();
    formData.append('image', window._sketchFile);

    try {
        const res = await fetch(`${API_BASE}/api/sketch`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'API error');
        }

        const data = await res.json();
        removeLastMessage();

        if (data.status === 'placeholder') {
            addMessage('system', `⚠️ ${data.message}`);
        } else if (data.svg) {
            showSvg(data.svg);
            currentSpec = data.spec;
            addMessage('system', '✅ Sketch reconstructed! Check the preview panel.');
        }
    } catch (e) {
        removeLastMessage();
        addMessage('system', `❌ Error: ${e.message}`);
    }

    // Reset upload
    uploadZone.classList.remove('hidden');
    uploadPreview.classList.add('hidden');
    window._sketchFile = null;
});

// ── SVG Preview ──────────────────────────────────────────────────
function showSvg(svgString) {
    currentSvg = svgString;
    svgContainer.innerHTML = svgString;
    previewPlaceholder.classList.add('hidden');
    svgContainer.classList.remove('hidden');
    downloadBar.classList.remove('hidden');
    zoomLevel = 1;
    svgContainer.style.transform = `scale(${zoomLevel})`;
}

// ── Zoom Controls ────────────────────────────────────────────────
$('#zoom-in-btn').addEventListener('click', () => {
    zoomLevel = Math.min(zoomLevel + 0.2, 3);
    svgContainer.style.transform = `scale(${zoomLevel})`;
});

$('#zoom-out-btn').addEventListener('click', () => {
    zoomLevel = Math.max(zoomLevel - 0.2, 0.3);
    svgContainer.style.transform = `scale(${zoomLevel})`;
});

$('#zoom-reset-btn').addEventListener('click', () => {
    zoomLevel = 1;
    svgContainer.style.transform = `scale(1)`;
});

// ── Download Handlers ────────────────────────────────────────────
$('#download-svg-btn').addEventListener('click', () => {
    if (!currentSvg) return;
    const blob = new Blob([currentSvg], { type: 'image/svg+xml' });
    downloadBlob(blob, 'techfig-diagram.svg');
});

$('#download-png-btn').addEventListener('click', () => {
    if (!currentSvg) return;

    // Convert SVG to PNG via canvas
    const svgEl = svgContainer.querySelector('svg');
    if (!svgEl) return;

    const canvas = document.createElement('canvas');
    const rect = svgEl.getBoundingClientRect();
    canvas.width = rect.width * 2;  // 2x for retina
    canvas.height = rect.height * 2;

    const ctx = canvas.getContext('2d');
    ctx.scale(2, 2);

    const img = new Image();
    const svgData = new XMLSerializer().serializeToString(svgEl);
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    img.onload = () => {
        ctx.drawImage(img, 0, 0, rect.width, rect.height);
        URL.revokeObjectURL(url);
        canvas.toBlob((blob) => {
            downloadBlob(blob, 'techfig-diagram.png');
        }, 'image/png');
    };
    img.src = url;
});

$('#copy-spec-btn').addEventListener('click', () => {
    if (!currentSpec) return;
    navigator.clipboard.writeText(JSON.stringify(currentSpec, null, 2))
        .then(() => {
            const btn = $('#copy-spec-btn');
            btn.textContent = '✓ Copied!';
            setTimeout(() => { btn.textContent = 'Copy JSON Spec'; }, 1500);
        });
});

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// ── Chat Message Helpers ─────────────────────────────────────────
function addMessage(type, text) {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.innerHTML = `<p>${escapeHtml(text)}</p>`;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function removeLastMessage() {
    const last = messagesEl.lastElementChild;
    if (last) last.remove();
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Smooth scroll for hero CTA ───────────────────────────────────
$('#try-demo-btn').addEventListener('click', (e) => {
    e.preventDefault();
    document.getElementById('demo').scrollIntoView({ behavior: 'smooth' });
});

// ── Init ─────────────────────────────────────────────────────────
renderTemplateGrid();
