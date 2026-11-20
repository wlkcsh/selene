// Parameterized JXA script to create an Apple Calendar event without stealing focus.
// Arguments:
// argv[0] = title (required)
// argv[1] = start_iso (ISO 8601 or parseable date string, required)
// argv[2] = end_iso (ISO 8601 or parseable date string, optional / 'none')
// argv[3] = calendar_name (optional / 'none' / 'default')
// argv[4] = notes (optional / 'none')
// argv[5] = location (optional / 'none')

function run(argv) {
    if (!argv || argv.length < 2) {
        return JSON.stringify({ ok: false, error: "Missing required arguments: title and start_iso" });
    }

    var title = argv[0];
    var startStr = argv[1];
    var endStr = (argv.length > 2 && argv[2] !== "none" && argv[2] !== "") ? argv[2] : null;
    var calName = (argv.length > 3 && argv[3] !== "none" && argv[3] !== "default" && argv[3] !== "") ? argv[3] : null;
    var notes = (argv.length > 4 && argv[4] !== "none" && argv[4] !== "") ? argv[4] : null;
    var loc = (argv.length > 5 && argv[5] !== "none" && argv[5] !== "") ? argv[5] : null;

    var Calendar = Application("Calendar");

    var targetCal = null;
    if (calName) {
        var matches = Calendar.calendars.whose({ name: calName });
        if (matches.length > 0) {
            targetCal = matches[0];
        }
    }

    if (!targetCal) {
        var writable = Calendar.calendars.whose({ writable: true });
        if (writable.length > 0) {
            targetCal = writable[0];
        } else {
            targetCal = Calendar.calendars[0];
        }
    }

    var startDate = new Date(startStr);
    if (isNaN(startDate.getTime())) {
        return JSON.stringify({ ok: false, error: "Invalid start date format: " + startStr });
    }

    var endDate;
    if (endStr) {
        endDate = new Date(endStr);
        if (isNaN(endDate.getTime())) {
            endDate = new Date(startDate.getTime() + 3600000);
        }
    } else {
        endDate = new Date(startDate.getTime() + 3600000); // 1 hour default
    }

    var props = {
        summary: title,
        startDate: startDate,
        endDate: endDate
    };
    if (notes) props.description = notes;
    if (loc) props.location = loc;

    var ev = Calendar.Event(props);
    targetCal.events.push(ev);

    return JSON.stringify({
        ok: true,
        id: ev.id(),
        title: ev.summary(),
        calendar: targetCal.name(),
        start: startDate.toISOString(),
        end: endDate.toISOString()
    });
}
