function run(argv) {
    const safari = Application("Safari");
    if (!safari.running() || safari.windows.length === 0) {
        return JSON.stringify({ error: "No open Safari window" });
    }
    try {
        const tab = safari.windows[0].currentTab();
        return JSON.stringify({
            title: tab.name(),
            url: tab.url()
        });
    } catch (e) {
        return JSON.stringify({ error: e.toString() });
    }
}
