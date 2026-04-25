(function () {
    const STORAGE_KEY = 'theme-preference';
    const TOGGLE_BTN_ID = 'theme-toggle-btn';

    // 1. Helper to get preference
    function getPreferredTheme() {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) return stored;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    // 2. Helper to set theme
    function setTheme(theme) {
        if (theme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
        }
        localStorage.setItem(STORAGE_KEY, theme);
        updateIcon(theme);
    }

    // 3. Update Button Icon
    function updateIcon(theme) {
        const btn = document.getElementById(TOGGLE_BTN_ID);
        if (!btn) return;
        // Moon for Dark, Sun for Light (or vice versa logic)
        // If current is dark, show Sun to switch to light.
        // If current is light, show Moon to switch to dark.
        btn.textContent = theme === 'dark' ? '🌙' : '☀️';
        btn.title = theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối';
    }

    // 4. Init
    function initTheme() {
        const currentTheme = getPreferredTheme();
        setTheme(currentTheme);

        // Create Button if not exists
        if (!document.getElementById(TOGGLE_BTN_ID)) {
            const btn = document.createElement('button');
            btn.id = TOGGLE_BTN_ID;
            btn.type = 'button';
            document.body.appendChild(btn);

            // Initial Icon
            updateIcon(currentTheme);

            // Event Listener
            btn.addEventListener('click', () => {
                const current = document.documentElement.getAttribute('data-theme') || 'light';
                const newTheme = current === 'light' ? 'dark' : 'light';
                setTheme(newTheme);
            });
        }
    }

    // Run on load (or immediate if body exists)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
})();
