// Parameterized JXA script to query Apple Calendar events without stealing focus.
// Arguments:
// argv[0] = days_ahead (integer, default 7)
// argv[1] = calendar_name (optional / 'none' / 'all')

function run(argv) {
    var daysAhead = 7;
    if (argv && argv.length > 0 && argv[0] !== "none" && argv[0] !== "") {
        var parsed = parseInt(argv[0], 10);
        if (!isNaN(parsed) && parsed > 0) daysAhead = parsed;
    }

    var calFilter = (argv && argv.length > 1 && argv[1] !== "none" && argv[1] !== "all" && argv[1] !== "") ? argv[1] : null;

    var Calendar = Application("Calendar");
    var now = new Date();
    var startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
    var endDate = new Date(startDate.getTime() + daysAhead * 24 * 60 * 60 * 1000);

    var cals = Calendar.calendars();
    var results = [];

    for (var i = 0; i < cals.length; i++) {
        var cal = cals[i];
        var cName = cal.name();

        if (calFilter) {
            if (cName.toLowerCase() !== calFilter.toLowerCase()) continue;
        } else {
            // Skip Siri suggestions and virtual reminder mirrors that cause CalDAV sync pauses
            if (cName.indexOf("Siri Suggestions") !== -1 || cName.indexOf("Scheduled Reminders") !== -1) {
                continue;
            }
        }

        try {
            var evs = cal.events.whose({
                _and: [
                    { startDate: { _greaterThanEquals: startDate } },
                    { startDate: { _lessThanEquals: endDate } }
                ]
            })();

            for (var j = 0; j < evs.length; j++) {
                var e = evs[j];
                results.push({
                    calendar: cName,
                    summary: e.summary(),
                    start: e.startDate().toISOString(),
                    end: e.endDate().toISOString(),
                    location: e.location() || "",
                    notes: e.description() || ""
                });
            }
        } catch (err) {
            // Skip calendars that fail filter
        }
    }

    results.sort(function(a, b) {
        return new Date(a.start) - new Date(b.start);
    });

    return JSON.stringify({ ok: true, count: results.length, events: results });
}
