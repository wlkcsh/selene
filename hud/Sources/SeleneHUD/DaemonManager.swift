import AppKit
import Foundation
import Observation

@Observable
@MainActor
public final class DaemonManager {
    public enum DaemonStatus: String, Sendable {
        case stopped = "Stopped"
        case starting = "Starting..."
        case running = "Running"
        case error = "Error"
    }

    public var status: DaemonStatus = .stopped
    public var lastError: String? = nil
    public var autoStart: Bool {
        didSet {
            UserDefaults.standard.set(autoStart, forKey: "selene_auto_start_daemon")
        }
    }

    private var process: Process?
    private var logFileHandle: FileHandle?
    public let logURL: URL
    public let projectPath: String

    public init() {
        self.autoStart = UserDefaults.standard.object(forKey: "selene_auto_start_daemon") as? Bool ?? true

        let home = FileManager.default.homeDirectoryForCurrentUser
        let logDir = home.appendingPathComponent("Library/Logs/Selene")
        try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
        self.logURL = logDir.appendingPathComponent("selene.log")

        if let envRoot = ProcessInfo.processInfo.environment["SELENE_PROJECT_ROOT"], !envRoot.isEmpty {
            self.projectPath = envRoot
        } else if let saved = UserDefaults.standard.string(forKey: "selene_project_root"), !saved.isEmpty {
            self.projectPath = saved
        } else {
            self.projectPath = home.appendingPathComponent("selene").path
        }
    }

    public func findUvBinary() -> URL? {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let candidates = [
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv",
            home.appendingPathComponent(".cargo/bin/uv").path,
            home.appendingPathComponent(".local/bin/uv").path,
            "/usr/bin/uv"
        ]

        for path in candidates {
            if FileManager.default.isExecutableFile(atPath: path) {
                return URL(fileURLWithPath: path)
            }
        }
        return nil
    }

    private func resolveGeminiApiKey() -> String? {
        if let key = ProcessInfo.processInfo.environment["GEMINI_API_KEY"], !key.isEmpty {
            return key
        }
        let zshrc = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".zshrc")
        if let content = try? String(contentsOf: zshrc, encoding: .utf8) {
            for line in content.components(separatedBy: .newlines) {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.contains("GEMINI_API_KEY=") && !trimmed.hasPrefix("#") {
                    let parts = trimmed.components(separatedBy: "GEMINI_API_KEY=")
                    if parts.count >= 2 {
                        let raw = parts[1].trimmingCharacters(in: CharacterSet(charactersIn: "\"' "))
                        if !raw.isEmpty {
                            return raw
                        }
                    }
                }
            }
        }
        return nil
    }

    public func startDaemon() {
        guard process == nil || !(process?.isRunning ?? false) else {
            status = .running
            return
        }

        guard let uvURL = findUvBinary() else {
            lastError = "Could not find 'uv' binary in standard paths (/opt/homebrew/bin/uv, ~/.cargo/bin/uv)."
            status = .error
            return
        }

        guard FileManager.default.fileExists(atPath: projectPath) else {
            lastError = "Selene project directory not found at \(projectPath)."
            status = .error
            return
        }

        status = .starting
        lastError = nil

        // Open or create log file
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }
        logFileHandle = try? FileHandle(forWritingTo: logURL)
        logFileHandle?.seekToEndOfFile()

        let banner = "\n=== [\(Date())] Starting Selene Daemon via Selene.app ===\n"
        if let data = banner.data(using: .utf8) {
            logFileHandle?.write(data)
        }

        var env = ProcessInfo.processInfo.environment
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let extraPaths = "/opt/homebrew/bin:/usr/local/bin:\(home)/.cargo/bin:\(home)/.local/bin"
        if let currentPath = env["PATH"] {
            env["PATH"] = "\(extraPaths):\(currentPath)"
        } else {
            env["PATH"] = "\(extraPaths):/usr/bin:/bin:/usr/sbin:/sbin"
        }
        env["PYTHONUNBUFFERED"] = "1"
        if env["GEMINI_API_KEY"] == nil, let key = resolveGeminiApiKey() {
            env["GEMINI_API_KEY"] = key
        }

        let proc = Process()
        proc.executableURL = uvURL
        proc.arguments = ["run", "--project", projectPath, "selene-voice", "--fast", "--daemon"]
        proc.currentDirectoryURL = URL(fileURLWithPath: projectPath)
        proc.environment = env

        if let handle = logFileHandle {
            proc.standardOutput = handle
            proc.standardError = handle
        }

        proc.terminationHandler = { [weak self] p in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                self.process = nil
                try? self.logFileHandle?.close()
                self.logFileHandle = nil
                if self.status != .stopped {
                    self.status = .stopped
                }
            }
        }

        do {
            try proc.run()
            self.process = proc
            self.status = .running
        } catch {
            self.status = .error
            self.lastError = "Failed to launch Selene daemon: \(error.localizedDescription)"
        }
    }

    public func stopDaemon() {
        guard let proc = process, proc.isRunning else {
            status = .stopped
            process = nil
            return
        }

        proc.terminate()
        process = nil
        status = .stopped
    }

    public func restartDaemon() {
        stopDaemon()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.startDaemon()
        }
    }

    public func openLogs() {
        if FileManager.default.fileExists(atPath: logURL.path) {
            NSWorkspace.shared.open(logURL)
        }
    }
}
