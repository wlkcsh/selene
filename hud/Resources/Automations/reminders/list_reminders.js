// Parameterized JXA script to list Apple Reminders without stealing focus.
// Arguments:
// argv[0] = list_name (optional / 'none' / 'all')
// argv[1] = include_completed ('true' or 'false', default 'false')

function run(argv) {
    var listFilter = (argv && argv.length > 0 && argv[0] !== "none" && argv[0] !== "all" && argv[0] !== "") ? argv[0] : null;
    var includeCompleted = (argv && argv.length > 1 && argv[1] === "true");

    var Reminders = Application("Reminders");
    var lists = Reminders.lists();
    var results = [];

    for (var i = 0; i < lists.length; i++) {
        var lst = lists[i];
        var lName = lst.name();
        if (listFilter && lName.toLowerCase() !== listFilter.toLowerCase()) {
            continue;
        }

        try {
            var rems;
            if (includeCompleted) {
                rems = lst.reminders();
            } else {
                rems = lst.reminders.whose({ completed: false })();
            }

            for (var j = 0; j < rems.length; j++) {
                var r = rems[j];
                var dDate = null;
                try {
                    var d = r.dueDate();
                    if (d) dDate = d.toISOString();
                } catch (e) {}

                results.push({
                    id: r.id(),
                    list: lName,
                    name: r.name(),
                    completed: r.completed(),
                    dueDate: dDate,
                    priority: r.priority()
                });
            }
        } catch (err) {
            // Skip failing lists
        }
    }

    return JSON.stringify({ ok: true, count: results.length, reminders: results });
}
