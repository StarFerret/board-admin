import AppKit
import Foundation

/// Runs the bundled install-starferret.sh and turns its output into state the window shows.
///
/// The app never installs anything itself. Every change to the Mac is made by
/// install-starferret.sh, the same script the Terminal install runs, so there is one
/// install path to test.
@MainActor
final class Installer: ObservableObject {
    static let shared = Installer()

    enum Phase: Equatable {
        case idle
        case running
        case finished
        case failed(String)
    }

    enum Action { case install, uninstall }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var action: Action = .install
    @Published private(set) var stepIndex = 0
    @Published private(set) var stepTotal = 9
    @Published private(set) var stepTitle = ""
    @Published private(set) var downloadPercent: Int?
    @Published private(set) var downloadDetail = ""
    @Published private(set) var lastNote = ""
    @Published private(set) var installed = false

    let boardURL = URL(string: "http://127.0.0.1:7410")!
    let controlURL = URL(string: "http://127.0.0.1:7411")!

    private var process: Process?
    private var pipe: Pipe?
    private var buffer = Data()
    private var failure: String?
    private var log: FileHandle?

    var isRunning: Bool { phase == .running }

    var logURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/StarFerret/installer.log")
    }

    /// One short line for the menu bar while something is happening.
    var statusLine: String {
        guard isRunning else { return "" }
        if action == .uninstall { return "Removing StarFerret's services…" }
        if let percent = downloadPercent { return "Downloading the model: \(percent)%" }
        return stepIndex > 0 ? "Installing: step \(stepIndex) of \(stepTotal)" : "Installing…"
    }

    init() {
        refreshInstalled()
    }

    func refreshInstalled() {
        let plist = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/com.starferret.board.plist")
        installed = FileManager.default.fileExists(atPath: plist.path)
    }

    // STARFERRET_INSTALL_SCRIPT points the app at another script. Only for testing the app.
    private var scriptURL: URL? {
        if let path = ProcessInfo.processInfo.environment["STARFERRET_INSTALL_SCRIPT"], !path.isEmpty {
            return URL(fileURLWithPath: path)
        }
        return Bundle.main.url(forResource: "install-starferret", withExtension: "sh")
    }

    private var bundleURL: URL? {
        Bundle.main.url(forResource: "starferret-macos", withExtension: "tar.gz")
    }

    func install() { run(arguments: [], action: .install) }

    func confirmUninstall() {
        let alert = NSAlert()
        alert.messageText = "Remove StarFerret's services?"
        alert.informativeText = "The Board, Control, LibreChat, and n8n stop and no longer start with this Mac. Your data and your models are kept, so installing again picks up where you left off."
        alert.addButton(withTitle: "Remove")
        alert.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertFirstButtonReturn {
            run(arguments: ["--uninstall"], action: .uninstall)
        }
    }

    func stop() {
        process?.terminate()
    }

    func open(_ url: URL) {
        NSWorkspace.shared.open(url)
    }

    func showLog() {
        NSWorkspace.shared.open(logURL)
    }

    private func run(arguments: [String], action: Action) {
        guard !isRunning else { return }
        guard let script = scriptURL, FileManager.default.fileExists(atPath: script.path) else {
            phase = .failed("This copy of StarFerret is missing its installer. Download StarFerret again.")
            return
        }
        self.action = action
        stepIndex = 0
        stepTitle = ""
        downloadPercent = nil
        downloadDetail = ""
        lastNote = ""
        failure = nil
        buffer = Data()

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")   // the stock bash 3.2 the script is written for
        process.arguments = [script.path] + arguments
        var env = ProcessInfo.processInfo.environment
        env["STARFERRET_GUI"] = "1"
        if let bundle = bundleURL, env["STARFERRET_BUNDLE"] == nil {
            env["STARFERRET_BUNDLE"] = bundle.path
        }
        // Apps start with a short PATH. Put the system tools first.
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin" + (env["PATH"].map { ":" + $0 } ?? "")
        process.environment = env
        process.standardInput = FileHandle.nullDevice

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        // The main queue runs these in order, so output is always handled before the end.
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            DispatchQueue.main.async { Installer.shared.receive(data) }
        }
        process.terminationHandler = { finished in
            let status = finished.terminationStatus
            DispatchQueue.main.async { Installer.shared.finish(status: status) }
        }

        openLog(action: action)
        do {
            try process.run()
            self.process = process
            self.pipe = pipe
            phase = .running
        } catch {
            pipe.fileHandleForReading.readabilityHandler = nil
            phase = .failed("The installer could not start: \(error.localizedDescription)")
        }
    }

    private func openLog(action: Action) {
        let folder = logURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }
        log = try? FileHandle(forWritingTo: logURL)
        _ = try? log?.seekToEnd()
        let stamp = ISO8601DateFormatter().string(from: Date())
        write(toLog: "\n===== \(stamp) \(action == .install ? "install" : "uninstall") =====\n")
    }

    private func write(toLog text: String) {
        if let data = text.data(using: .utf8) { try? log?.write(contentsOf: data) }
    }

    private func receive(_ data: Data) {
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 0x0A) {
            let lineData = buffer[buffer.startIndex..<newline]
            buffer.removeSubrange(buffer.startIndex...newline)
            handle(String(decoding: lineData, as: UTF8.self))
        }
    }

    private func handle(_ line: String) {
        write(toLog: line + "\n")
        switch parseInstallerLine(line) {
        case let .step(index, total, title):
            stepIndex = index
            stepTotal = total
            stepTitle = title
            downloadPercent = nil
            downloadDetail = ""
            lastNote = ""
        case let .download(_, percent, detail):
            downloadPercent = percent
            downloadDetail = detail
        case let .stopped(message):
            failure = message
        case let .done(message), let .warning(message):
            lastNote = message
        case .other, .blank:
            break
        }
    }

    private func finish(status: Int32) {
        if let pipe {
            pipe.fileHandleForReading.readabilityHandler = nil
            receive(pipe.fileHandleForReading.readDataToEndOfFile())
        }
        if !buffer.isEmpty {
            handle(String(decoding: buffer, as: UTF8.self))
            buffer = Data()
        }
        write(toLog: "===== exit \(status) =====\n")
        try? log?.close()
        log = nil
        process = nil
        pipe = nil
        refreshInstalled()
        if status == 0 {
            phase = .finished
        } else {
            phase = .failed(failure ?? "The installer stopped before it finished. The log says why.")
        }
    }
}
