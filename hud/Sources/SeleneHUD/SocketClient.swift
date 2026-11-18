import Darwin
import Foundation

public final class SocketClient: @unchecked Sendable {
    private let socketPath: String
    private let onEvent: @MainActor @Sendable (HUDEvent) -> Void
    private let onConnectionChange: @MainActor @Sendable (Bool) -> Void
    private let queue = DispatchQueue(label: "selene.socket.client", qos: .userInteractive)

    private var isRunning = false
    private var currentFd: Int32 = -1
    private let lock = NSLock()

    public init(
        socketPath: String = "/tmp/selene.sock",
        onEvent: @escaping @MainActor @Sendable (HUDEvent) -> Void,
        onConnectionChange: @escaping @MainActor @Sendable (Bool) -> Void
    ) {
        self.socketPath = socketPath
        self.onEvent = onEvent
        self.onConnectionChange = onConnectionChange
    }

    public func start() {
        lock.lock()
        guard !isRunning else {
            lock.unlock()
            return
        }
        isRunning = true
        lock.unlock()

        queue.async { [weak self] in
            self?.runLoop()
        }
    }

    public func stop() {
        lock.lock()
        isRunning = false
        if currentFd >= 0 {
            close(currentFd)
            currentFd = -1
        }
        lock.unlock()
    }

    public func sendCommand(_ command: HUDCommand) {
        lock.lock()
        defer { lock.unlock() }
        guard currentFd >= 0 else { return }

        do {
            var data = try JSONEncoder().encode(command)
            data.append(contentsOf: [0x0A]) // Newline
            _ = data.withUnsafeBytes { raw in
                write(currentFd, raw.baseAddress, raw.count)
            }
        } catch {
            // Ignore write errors
        }
    }

    private func runLoop() {
        let decoder = JSONDecoder()

        while true {
            lock.lock()
            if !isRunning {
                lock.unlock()
                break
            }
            lock.unlock()

            let fd = socket(AF_UNIX, SOCK_STREAM, 0)
            if fd < 0 {
                Thread.sleep(forTimeInterval: 1.0)
                continue
            }

            var addr = sockaddr_un()
            addr.sun_family = sa_family_t(AF_UNIX)
            _ = withUnsafeMutablePointer(to: &addr.sun_path.0) { ptr in
                socketPath.withCString { cstr in
                    strcpy(ptr, cstr)
                }
            }

            let connectRes = withUnsafePointer(to: &addr) { ptr in
                ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                    connect(fd, sa, socklen_t(MemoryLayout<sockaddr_un>.size))
                }
            }

            if connectRes != 0 {
                close(fd)
                Task { @MainActor in
                    self.onConnectionChange(false)
                }
                Thread.sleep(forTimeInterval: 1.0)
                continue
            }

            lock.lock()
            currentFd = fd
            lock.unlock()

            Task { @MainActor in
                self.onConnectionChange(true)
            }

            var buffer = Data()
            var readBuf = [UInt8](repeating: 0, count: 2048)

            while true {
                let n = read(fd, &readBuf, readBuf.count)
                if n <= 0 {
                    break
                }
                buffer.append(readBuf, count: n)

                while let newlineIdx = buffer.firstIndex(of: 0x0A) {
                    let lineData = buffer.subdata(in: 0..<newlineIdx)
                    buffer.removeSubrange(0...newlineIdx)

                    if let event = try? decoder.decode(HUDEvent.self, from: lineData) {
                        Task { @MainActor in
                            self.onEvent(event)
                        }
                    }
                }
            }

            lock.lock()
            if currentFd == fd {
                currentFd = -1
            }
            lock.unlock()
            close(fd)

            Task { @MainActor in
                self.onConnectionChange(false)
            }
            Thread.sleep(forTimeInterval: 1.0)
        }
    }
}
