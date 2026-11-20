// Parameterized JXA script to create an Apple Reminder without stealing focus.
// Arguments:
// argv[0] = title (required)
// argv[1] = due_iso (ISO 8601 or date string, optional / 'none')
// argv[2] = list_name (optional / 'none' / 'default')
// argv[3] = notes (optional / 'none')
// argv[4] = priority (integer 0=none, 1=high, 5=medium, 9=low, default 0)

function run(argv) {
    if (!argv || argv.length < 1) {
        return JSON.stringify({ ok: false, error: "Missing required argument: title" });
    }

    var title = argv[0];
    var dueStr = (argv.length > 1 && argv[1] !== "none" && argv[1] !== "") ? argv[1] : null;
    var listName = (argv.length > 2 && argv[2] !== "none" && argv[2] !== "default" && argv[2] !== "") ? argv[2] : null;
    var notes = (argv.length > 3 && argv[3] !== "none" && argv[3] !== "") ? argv[3] : null;
    var prio = (argv.length > 4 && argv[4] !== "none" && argv[4] !== "") ? parseInt(argv[4], 10) : 0;

    var Reminders = Application("Reminders");

    var targetList = null;
    if (listName) {
        var matches = Reminders.lists.whose({ name: listName });
        if (matches.length > 0) targetList = matches[0];
    }
    if (!targetList) {
        targetList = Reminders.defaultList();
    }

    var props = { name: title };
    if (dueStr) {
        var d = new Date(dueStr);
        if (!isNaN(d.getTime())) {
            props.dueDate = d;
        }
    }
    if (notes) props.body = notes;
    if (!isNaN(prio) && prio > 0) props.priority = prio;

    var rem = Reminders.Reminder(props);
    targetList.reminders.push(rem);

    return JSON.stringify({
        ok: true,
        id: rem.id(),
        name: rem.name(),
        list: targetList.name(),
        dueDate: props.dueDate ? props.dueDate.toISOString() : null
    });
}
