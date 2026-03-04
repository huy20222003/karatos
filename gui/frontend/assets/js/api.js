/**
 * Karatos API Client — Fetch wrapper for all backend endpoints.
 */
const API = {
    BASE: '/api',

    async get(path) {
        try {
            const res = await fetch(`${this.BASE}${path}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error(`[API] GET ${path} failed:`, e);
            return { error: e.message };
        }
    },

    async post(path, body) {
        try {
            const res = await fetch(`${this.BASE}${path}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || `HTTP ${res.status}`);
            }
            return await res.json();
        } catch (e) {
            console.error(`[API] POST ${path} failed:`, e);
            return { error: e.message };
        }
    },

    async del(path) {
        try {
            const res = await fetch(`${this.BASE}${path}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error(`[API] DELETE ${path} failed:`, e);
            return { error: e.message };
        }
    }
};

/** Show a toast notification */
function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

/** UI Helpers */
const UI = {
    setLoading(btn, isLoading) {
        if (!btn) return;
        if (isLoading) {
            btn.classList.add('btn-loading');
            btn.disabled = true;
        } else {
            btn.classList.remove('btn-loading');
            btn.disabled = false;
        }
    },

    showError(inputEl, message) {
        this.clearError(inputEl);
        inputEl.classList.add('input-error');
        const err = document.createElement('div');
        err.className = 'error-msg';
        err.style.color = 'var(--red)';
        err.style.fontSize = '11px';
        err.style.marginTop = '4px';
        err.innerText = message;
        inputEl.parentNode.appendChild(err);
    },

    clearError(inputEl) {
        inputEl.classList.remove('input-error');
        const existing = inputEl.parentNode.querySelector('.error-msg');
        if (existing) existing.remove();
    }
};

/** Input Validation Logic */
const Validator = {
    isJSON(str) {
        if (!str || !str.trim()) return true; // Empty is fine for some cases
        try {
            JSON.parse(str);
            return true;
        } catch (e) {
            return false;
        }
    },

    isSafeName(str) {
        return /^[a-z0-9\-_]+$/i.test(str);
    },

    isURL(str) {
        try {
            new URL(str);
            return true;
        } catch (e) {
            return false;
        }
    },

    sanitize(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};
