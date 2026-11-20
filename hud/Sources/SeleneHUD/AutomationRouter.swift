import Foundation

public struct ScriptSpec: Sendable {
    public let bundleID: String
    public let resourceSubpath: String
    public let language: String
    public let timeoutSeconds: Double

    public init(
        bundleID: String,
        resourceSubpath: String,
        language: String = "AppleScript",
        timeoutSeconds: Double = 5.0
    ) {
        self.bundleID = bundleID
        self.resourceSubpath = resourceSubpath
        self.language = language
        self.timeoutSeconds = timeoutSeconds
    }
}

final class PipeAccumulator: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()

    func append(_ chunk: Data) {
        guard !chunk.isEmpty else { return }
        lock.lock()
        data.append(chunk)
        lock.unlock()
    }

    func collect() -> Data {
        lock.lock()
        defer { lock.unlock() }
        return data
    }
}

public actor AutomationRouter {
    private let permissionGuard = AutomationPermissionGuard()
    private let eventKitAdapter = EventKitAdapter()

    private let registry: [String: ScriptSpec] = [
        "spotify.play_uri": ScriptSpec(
            bundleID: "com.spotify.client",
            resourceSubpath: "spotify/play_uri.applescript",
            language: "AppleScript",
            timeoutSeconds: 5.0
        ),
        "spotify.control": ScriptSpec(
            bundleID: "com.spotify.client",
            resourceSubpath: "spotify/control.applescript",
            language: "AppleScript",
            timeoutSeconds: 4.0
        ),
        "safari.active_tab": ScriptSpec(
            bundleID: "com.apple.Safari",
            resourceSubpath: "safari/active_tab.js",
            language: "JavaScript",
            timeoutSeconds: 3.0
        ),
        "notes.create_note": ScriptSpec(
            bundleID: "com.apple.Notes",
            resourceSubpath: "notes/create_note.js",
            language: "JavaScript",
            timeoutSeconds: 6.0
        )
    ]

    public init() {}

    public func handle(_ request: AutomationRequest) async -> AutomationResponse {
        // 1. Direct native Swift EventKit routes (Calendar & Reminders)
        if request.app == "calendar" || request.app == "reminders" {
            return await handleEventKit(request)
        }

        // 2. Script-based routes (Spotify, Safari, Notes)
        let key = "\(request.app).\(request.action)"
        guard let spec = registry[key] else {
            return AutomationResponse(
                reqId: request.reqId,
                ok: false,
                output: nil,
                errorCode: "unknown_action",
                errorMessage: "No automation adapter registered for '\(key)'"
            )
        }

        // TCC Pre-Flight Check for script target
        let auth = await permissionGuard.ensureAuthorized(bundleID: spec.bundleID)
        switch auth {
        case .granted:
            break
        case .denied:
            return AutomationResponse(
                reqId: request.reqId,
                ok: false,
                output: nil,
                errorCode: "permission_denied",
                errorMessage: "Automation permission denied for \(spec.bundleID). Please allow it in System Settings -> Privacy & Security -> Automation."
            )
        case .targetNotRunning, .needsPrompt:
            return AutomationResponse(
                reqId: request.reqId,
                ok: false,
                output: nil,
                errorCode: "target_unavailable",
                errorMessage: "Could not reach target application \(spec.bundleID) (\(auth.rawValue))."
            )
        }

        guard let scriptURL = resolveScriptURL(subpath: spec.resourceSubpath) else {
            return AutomationResponse(
                reqId: request.reqId,
                ok: false,
                output: nil,
                errorCode: "missing_script",
                errorMessage: "Automation script '\(spec.resourceSubpath)' not found in app bundle or dev paths."
            )
        }

        do {
            let stdout = try await runOSAScript(
                scriptPath: scriptURL.path,
                language: spec.language,
                args: request.args,
                timeout: spec.timeoutSeconds
            )
            return AutomationResponse(
                reqId: request.reqId,
                ok: true,
                output: stdout,
                errorCode: nil,
                errorMessage: nil
            )
        } catch {
            return AutomationResponse(
                reqId: request.reqId,
                ok: false,
                output: nil,
                errorCode: "execution_failed",
                errorMessage: error.localizedDescription
            )
        }
    }

    // MARK: - Native EventKit Dispatch

    private func handleEventKit(_ request: AutomationRequest) async -> AutomationResponse {
        let encoder = JSONEncoder()

        do {
            switch "\(request.app).\(request.action)" {
            case "calendar.create_event":
                guard request.args.count >= 2 else {
                    throw NSError(domain: "EventKit", code: -1, userInfo: [NSLocalizedDescriptionKey: "Missing title and start date arguments"])
                }
                let title = request.args[0]
                let startEpoch = parseEpochMs(from: request.args[1])
                let endEpoch: Double
                if request.args.count > 2 && request.args[2] != "none" && !request.args[2].isEmpty {
                    endEpoch = parseEpochMs(from: request.args[2])
                } else {
                    endEpoch = startEpoch + 3600000.0 // 1 hour default
                }
                let calName = request.args.count > 3 ? request.args[3] : nil
                let notes = request.args.count > 4 ? request.args[4] : nil
                let loc = request.args.count > 5 ? request.args[5] : nil

                let dto = try await eventKitAdapter.createEvent(
                    title: title,
                    startEpochMs: startEpoch,
                    endEpochMs: endEpoch,
                    calendarName: calName,
                    location: loc,
                    notes: notes
                )
                let data = try encoder.encode(dto)
                let output = String(data: data, encoding: .utf8)

                return AutomationResponse(
                    reqId: request.reqId,
                    ok: true,
                    output: output,
                    errorCode: nil,
                    errorMessage: nil
                )

            case "calendar.list_events":
                let nowMs = Date().timeIntervalSince1970 * 1000.0
                var startMs = nowMs
                var endMs = nowMs + 7 * 86400000.0
                var calFilter: String? = nil

                if !request.args.isEmpty {
                    if let firstArg = Double(request.args[0]) {
                        if firstArg < 1000.0 {
                            // Passed days_ahead
                            endMs = nowMs + firstArg * 86400000.0
                        } else {
                            // Passed startEpochMs
                            startMs = firstArg
                            if request.args.count > 1, let secondArg = Double(request.args[1]) {
                                endMs = secondArg
                            }
                        }
                    }
                }
                if request.args.count > 2 && request.args[2] != "none" && !request.args[2].isEmpty {
                    calFilter = request.args[2]
                } else if request.args.count > 1 && Double(request.args[0]) != nil && Double(request.args[0])! < 1000.0 {
                    calFilter = request.args[1] != "none" ? request.args[1] : nil
                }

                let events = try await eventKitAdapter.listEvents(
                    startEpochMs: startMs,
                    endEpochMs: endMs,
                    calendarFilter: calFilter
                )

                let dict: [String: Any] = [
                    "ok": true,
                    "count": events.count,
                    "events": events.map { ev in
                        [
                            "id": ev.id,
                            "calendar": ev.calendar,
                            "summary": ev.title,
                            "start": Date(timeIntervalSince1970: ev.startEpochMs / 1000.0).ISO8601Format(),
                            "end": Date(timeIntervalSince1970: ev.endEpochMs / 1000.0).ISO8601Format(),
                            "location": ev.location ?? "",
                            "notes": ev.notes ?? ""
                        ]
                    }
                ]
                let jsonData = try JSONSerialization.data(withJSONObject: dict)
                let output = String(data: jsonData, encoding: .utf8)

                return AutomationResponse(
                    reqId: request.reqId,
                    ok: true,
                    output: output,
                    errorCode: nil,
                    errorMessage: nil
                )

            case "reminders.create_reminder":
                guard !request.args.isEmpty else {
                    throw NSError(domain: "EventKit", code: -1, userInfo: [NSLocalizedDescriptionKey: "Missing reminder title"])
                }
                let title = request.args[0]
                var dueEpoch: Double? = nil
                if request.args.count > 1 && request.args[1] != "none" && !request.args[1].isEmpty {
                    dueEpoch = parseEpochMs(from: request.args[1])
                }
                let listName = request.args.count > 2 && request.args[2] != "none" ? request.args[2] : nil
                let notes = request.args.count > 3 && request.args[3] != "none" ? request.args[3] : nil
                let priority = request.args.count > 4 ? (Int(request.args[4]) ?? 0) : 0

                let dto = try await eventKitAdapter.createReminder(
                    title: title,
                    dueEpochMs: dueEpoch,
                    listName: listName,
                    notes: notes,
                    priority: priority
                )
                let data = try encoder.encode(dto)
                let output = String(data: data, encoding: .utf8)

                return AutomationResponse(
                    reqId: request.reqId,
                    ok: true,
                    output: output,
                    errorCode: nil,
                    errorMessage: nil
                )

            case "reminders.list_reminders":
                let listFilter = (request.args.count > 0 && request.args[0] != "none" && request.args[0] != "all") ? request.args[0] : nil
                let includeCompleted = (request.args.count > 1 && request.args[1] == "true")

                let reminders = try await eventKitAdapter.listReminders(
                    listFilter: listFilter,
                    includeCompleted: includeCompleted
                )

                let dict: [String: Any] = [
                    "ok": true,
                    "count": reminders.count,
                    "reminders": reminders.map { r in
                        [
                            "id": r.id,
                            "name": r.name,
                            "list": r.list,
                            "completed": r.completed,
                            "dueDate": r.dueEpochMs != nil ? Date(timeIntervalSince1970: r.dueEpochMs! / 1000.0).ISO8601Format() : NSNull(),
                            "priority": r.priority
                        ]
                    }
                ]
                let jsonData = try JSONSerialization.data(withJSONObject: dict)
                let output = String(data: jsonData, encoding: .utf8)

                return AutomationResponse(
                    reqId: request.reqId,
                    ok: true,
                    output: output,
                    errorCode: nil,
                    errorMessage: nil
                )

            default:
                return AutomationResponse(
                    reqId: request.reqId,
                    ok: false,
                    output: nil,
                    errorCode: "unknown_action",
                    errorMessage: "No EventKit action for '\(request.app).\(request.action)'"
                )
            }
        } catch {
            return AutomationResponse(
                reqId: request.reqId,
                ok: false,
                output: nil,
                errorCode: "eventkit_error",
                errorMessage: error.localizedDescription
            )
        }
    }

    private func parseEpochMs(from string: String) -> Double {
        if let val = Double(string) {
            return val
        }
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: string) {
            return date.timeIntervalSince1970 * 1000.0
        }
        return Date().timeIntervalSince1970 * 1000.0
    }

    private func resolveScriptURL(subpath: String) -> URL? {
        let fm = FileManager.default
        if let bundleRes = Bundle.main.resourceURL?.appendingPathComponent("Automations").appendingPathComponent(subpath),
           fm.fileExists(atPath: bundleRes.path) {
            return bundleRes
        }

        let currentFile = URL(fileURLWithPath: #filePath)
        let repoRoot = currentFile
            .deletingLastPathComponent() // SeleneHUD
            .deletingLastPathComponent() // Sources
            .deletingLastPathComponent() // hud
        let devURL = repoRoot
            .appendingPathComponent("Resources")
            .appendingPathComponent("Automations")
            .appendingPathComponent(subpath)
        if fm.fileExists(atPath: devURL.path) {
            return devURL
        }

        return nil
    }

    // MARK: - Safe OSAScript Runner with Concurrent Pipe Draining (Fixes 64 KB Deadlock)

    private func runOSAScript(
        scriptPath: String,
        language: String,
        args: [String],
        timeout: Double
    ) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            process.arguments = ["-l", language, scriptPath] + args

            let outPipe = Pipe()
            let errPipe = Pipe()
            process.standardOutput = outPipe
            process.standardError = errPipe

            let stdoutBuffer = PipeAccumulator()
            let stderrBuffer = PipeAccumulator()

            // Drain pipe concurrently while child process runs to prevent 64 KB buffer deadlock
            outPipe.fileHandleForReading.readabilityHandler = { handle in
                stdoutBuffer.append(handle.availableData)
            }

            errPipe.fileHandleForReading.readabilityHandler = { handle in
                stderrBuffer.append(handle.availableData)
            }

            let timeoutWork = DispatchWorkItem {
                if process.isRunning {
                    process.terminate()
                }
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: timeoutWork)

            process.terminationHandler = { proc in
                timeoutWork.cancel()

                // Remove readability handlers to stop monitoring
                outPipe.fileHandleForReading.readabilityHandler = nil
                errPipe.fileHandleForReading.readabilityHandler = nil

                // Read any remaining trailing bytes
                stdoutBuffer.append(outPipe.fileHandleForReading.readDataToEndOfFile())
                stderrBuffer.append(errPipe.fileHandleForReading.readDataToEndOfFile())

                let finalOut = stdoutBuffer.collect()
                let finalErr = stderrBuffer.collect()

                let outStr = String(data: finalOut, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let errStr = String(data: finalErr, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

                if proc.terminationStatus == 0 {
                    continuation.resume(returning: outStr)
                } else {
                    let errMsg = errStr.isEmpty ? "osascript exited with status \(proc.terminationStatus)" : errStr
                    let err = NSError(
                        domain: "SeleneAutomation",
                        code: Int(proc.terminationStatus),
                        userInfo: [NSLocalizedDescriptionKey: errMsg]
                    )
                    continuation.resume(throwing: err)
                }
            }

            do {
                try process.run()
            } catch {
                timeoutWork.cancel()
                outPipe.fileHandleForReading.readabilityHandler = nil
                errPipe.fileHandleForReading.readabilityHandler = nil
                continuation.resume(throwing: error)
            }
        }
    }
}
