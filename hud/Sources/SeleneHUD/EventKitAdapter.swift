import EventKit
import Foundation

public struct CalendarEventDTO: Codable, Sendable {
    public let id: String
    public let title: String
    public let calendar: String
    public let startEpochMs: Double
    public let endEpochMs: Double
    public let isAllDay: Bool
    public let location: String?
    public let notes: String?

    public init(
        id: String,
        title: String,
        calendar: String,
        startEpochMs: Double,
        endEpochMs: Double,
        isAllDay: Bool,
        location: String?,
        notes: String?
    ) {
        self.id = id
        self.title = title
        self.calendar = calendar
        self.startEpochMs = startEpochMs
        self.endEpochMs = endEpochMs
        self.isAllDay = isAllDay
        self.location = location
        self.notes = notes
    }
}

public struct ReminderDTO: Codable, Sendable {
    public let id: String
    public let name: String
    public let list: String
    public let completed: Bool
    public let dueEpochMs: Double?
    public let priority: Int

    public init(
        id: String,
        name: String,
        list: String,
        completed: Bool,
        dueEpochMs: Double?,
        priority: Int
    ) {
        self.id = id
        self.name = name
        self.list = list
        self.completed = completed
        self.dueEpochMs = dueEpochMs
        self.priority = priority
    }
}

public actor EventKitAdapter {
    private let store = EKEventStore()

    public init() {}

    // MARK: - Permissions

    public func ensureCalendarAccess() async throws {
        switch EKEventStore.authorizationStatus(for: .event) {
        case .fullAccess:
            return
        case .notDetermined:
            let granted = try await store.requestFullAccessToEvents()
            if !granted {
                throw EventKitError.permissionDenied("Calendar")
            }
        default:
            throw EventKitError.permissionDenied("Calendar")
        }
    }

    public func ensureRemindersAccess() async throws {
        switch EKEventStore.authorizationStatus(for: .reminder) {
        case .fullAccess:
            return
        case .notDetermined:
            let granted = try await store.requestFullAccessToReminders()
            if !granted {
                throw EventKitError.permissionDenied("Reminders")
            }
        default:
            throw EventKitError.permissionDenied("Reminders")
        }
    }

    // MARK: - Calendar Operations

    public func listEvents(
        startEpochMs: Double,
        endEpochMs: Double,
        calendarFilter: String? = nil
    ) async throws -> [CalendarEventDTO] {
        try await ensureCalendarAccess()

        let startDate = Date(timeIntervalSince1970: startEpochMs / 1000.0)
        let maxEnd = Calendar.current.date(byAdding: .year, value: 2, to: startDate) ?? startDate
        let endDate = min(Date(timeIntervalSince1970: endEpochMs / 1000.0), maxEnd)

        // Filter out subscriptions and holiday/birthday virtual mirrors regardless of macOS language
        var activeCalendars = store.calendars(for: .event).filter { cal in
            cal.type != .subscription && cal.type != .birthday
        }

        if let filter = calendarFilter, !filter.isEmpty, filter != "none", filter != "all" {
            activeCalendars = activeCalendars.filter { cal in
                cal.title.localizedCaseInsensitiveCompare(filter) == .orderedSame
            }
        }

        // Native expansion of all RRULE recurrences, EXDATE exclusions, and modified instances
        let predicate = store.predicateForEvents(
            withStart: startDate,
            end: endDate,
            calendars: activeCalendars
        )

        return store.events(matching: predicate)
            .sorted { $0.startDate < $1.startDate }
            .map { ev in
                CalendarEventDTO(
                    id: ev.eventIdentifier ?? "",
                    title: ev.title ?? "(Untitled)",
                    calendar: ev.calendar.title,
                    startEpochMs: ev.startDate.timeIntervalSince1970 * 1000.0,
                    endEpochMs: ev.endDate.timeIntervalSince1970 * 1000.0,
                    isAllDay: ev.isAllDay,
                    location: ev.location,
                    notes: ev.notes
                )
            }
    }

    public func createEvent(
        title: String,
        startEpochMs: Double,
        endEpochMs: Double,
        calendarName: String? = nil,
        location: String? = nil,
        notes: String? = nil
    ) async throws -> CalendarEventDTO {
        try await ensureCalendarAccess()

        let event = EKEvent(eventStore: store)
        event.title = title
        event.startDate = Date(timeIntervalSince1970: startEpochMs / 1000.0)
        event.endDate = Date(timeIntervalSince1970: endEpochMs / 1000.0)

        if let loc = location, loc != "none", !loc.isEmpty {
            event.location = loc
        }
        if let n = notes, n != "none", !n.isEmpty {
            event.notes = n
        }

        let writable = store.calendars(for: .event).filter(\.allowsContentModifications)
        if let name = calendarName, name != "none", name != "default", !name.isEmpty,
           let matched = writable.first(where: { $0.title.localizedCaseInsensitiveCompare(name) == .orderedSame }) {
            event.calendar = matched
        } else if let defaultCal = store.defaultCalendarForNewEvents, defaultCal.allowsContentModifications {
            event.calendar = defaultCal
        } else if let firstWritable = writable.first {
            event.calendar = firstWritable
        } else {
            throw EventKitError.noWritableCalendar
        }

        try store.save(event, span: .thisEvent, commit: true)

        return CalendarEventDTO(
            id: event.eventIdentifier ?? "",
            title: event.title ?? title,
            calendar: event.calendar.title,
            startEpochMs: event.startDate.timeIntervalSince1970 * 1000.0,
            endEpochMs: event.endDate.timeIntervalSince1970 * 1000.0,
            isAllDay: event.isAllDay,
            location: event.location,
            notes: event.notes
        )
    }

    // MARK: - Reminders Operations

    public func listReminders(
        listFilter: String? = nil,
        includeCompleted: Bool = false
    ) async throws -> [ReminderDTO] {
        try await ensureRemindersAccess()

        var activeCalendars = store.calendars(for: .reminder)
        if let filter = listFilter, !filter.isEmpty, filter != "none", filter != "all" {
            activeCalendars = activeCalendars.filter { cal in
                cal.title.localizedCaseInsensitiveCompare(filter) == .orderedSame
            }
        }

        let predicate = includeCompleted
            ? store.predicateForReminders(in: activeCalendars)
            : store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: activeCalendars)

        let rawReminders: [EKReminder] = try await withCheckedThrowingContinuation { continuation in
            store.fetchReminders(matching: predicate) { found in
                continuation.resume(returning: found ?? [])
            }
        }

        return rawReminders
            .sorted { r1, r2 in
                let d1 = r1.dueDateComponents?.date ?? Date.distantFuture
                let d2 = r2.dueDateComponents?.date ?? Date.distantFuture
                return d1 < d2
            }
            .map { r in
                let dueEpoch: Double? = r.dueDateComponents?.date.map { $0.timeIntervalSince1970 * 1000.0 }
                return ReminderDTO(
                    id: r.calendarItemIdentifier,
                    name: r.title ?? "(Untitled)",
                    list: r.calendar.title,
                    completed: r.isCompleted,
                    dueEpochMs: dueEpoch,
                    priority: r.priority
                )
            }
    }

    public func createReminder(
        title: String,
        dueEpochMs: Double? = nil,
        listName: String? = nil,
        notes: String? = nil,
        priority: Int = 0
    ) async throws -> ReminderDTO {
        try await ensureRemindersAccess()

        let reminder = EKReminder(eventStore: store)
        reminder.title = title

        if let epoch = dueEpochMs, epoch > 0 {
            let dueDate = Date(timeIntervalSince1970: epoch / 1000.0)
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute],
                from: dueDate
            )
        }

        if let n = notes, n != "none", !n.isEmpty {
            reminder.notes = n
        }

        if priority > 0 {
            reminder.priority = min(9, max(1, priority))
        }

        let writable = store.calendars(for: .reminder).filter(\.allowsContentModifications)
        if let name = listName, name != "none", name != "default", !name.isEmpty,
           let matched = writable.first(where: { $0.title.localizedCaseInsensitiveCompare(name) == .orderedSame }) {
            reminder.calendar = matched
        } else if let defaultList = store.defaultCalendarForNewReminders() {
            reminder.calendar = defaultList
        } else if let firstWritable = writable.first {
            reminder.calendar = firstWritable
        } else {
            throw EventKitError.noWritableCalendar
        }

        try store.save(reminder, commit: true)

        let savedDue: Double? = reminder.dueDateComponents?.date.map { $0.timeIntervalSince1970 * 1000.0 }
        return ReminderDTO(
            id: reminder.calendarItemIdentifier,
            name: reminder.title ?? title,
            list: reminder.calendar.title,
            completed: reminder.isCompleted,
            dueEpochMs: savedDue,
            priority: reminder.priority
        )
    }

    // MARK: - Errors

    public enum EventKitError: LocalizedError, Equatable {
        case permissionDenied(String)
        case noWritableCalendar

        public var errorDescription: String? {
            switch self {
            case .permissionDenied(let domain):
                return "\(domain) access denied. Please enable Selene in System Settings -> Privacy & Security -> \(domain)."
            case .noWritableCalendar:
                return "No writable calendar or reminders list available."
            }
        }
    }
}
