import AppKit
import SwiftUI

// StarFerret for Mac: a window that runs the installer with a progress bar, then a
// menu bar item for opening the Board and Control. Built by ../build-dmg.sh with
// swiftc from the Xcode command line tools. No Xcode project, no packages.

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.activate(ignoringOtherApps: true)
        // Testing the app only: with a stand-in script, start without a click.
        let env = ProcessInfo.processInfo.environment
        if !(env["STARFERRET_INSTALL_SCRIPT"] ?? "").isEmpty && env["STARFERRET_AUTOSTART"] == "1" {
            Installer.shared.install()
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        let installer = Installer.shared
        guard installer.isRunning else { return .terminateNow }
        let alert = NSAlert()
        alert.messageText = "StarFerret is still installing"
        alert.informativeText = "If you quit now, the install stops. A model download that already started keeps going in Control. Open StarFerret again later to finish."
        alert.addButton(withTitle: "Keep installing")
        alert.addButton(withTitle: "Quit anyway")
        if alert.runModal() == .alertSecondButtonReturn {
            installer.stop()
            return .terminateNow
        }
        return .terminateCancel
    }
}

@main
struct StarFerretApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var installer = Installer.shared

    var body: some Scene {
        Window("StarFerret", id: "main") {
            InstallView()
                .environmentObject(installer)
                .frame(width: 460)
        }
        .windowResizability(.contentSize)

        MenuBarExtra {
            MenuContent()
                .environmentObject(installer)
        } label: {
            Image(systemName: "sparkles")
        }
    }
}

struct MenuContent: View {
    @EnvironmentObject private var installer: Installer
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        if installer.isRunning {
            Text(installer.statusLine)
            Divider()
        }
        if installer.installed {
            Button("Open the Board") { installer.open(installer.boardURL) }
            Button("Open Control") { installer.open(installer.controlURL) }
            Button("Check for updates") { installer.open(installer.controlURL.appendingPathComponent("updates")) }
            Divider()
        }
        Button("Show the StarFerret window") { showWindow() }
        Button(installer.installed ? "Repair or reinstall" : "Install StarFerret") {
            showWindow()
            installer.install()
        }
        .disabled(installer.isRunning)
        if installer.installed {
            Button("Remove StarFerret…") { installer.confirmUninstall() }
                .disabled(installer.isRunning)
        }
        Divider()
        // Quitting only removes the menu bar item. The Board and Control keep serving.
        Button("Quit menu bar item") { NSApp.terminate(nil) }
    }

    private func showWindow() {
        openWindow(id: "main")
        NSApp.activate(ignoringOtherApps: true)
    }
}

struct InstallView: View {
    @EnvironmentObject private var installer: Installer

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                Image(systemName: "sparkles")
                    .font(.system(size: 30))
                    .foregroundStyle(.green)
                VStack(alignment: .leading, spacing: 2) {
                    Text("StarFerret").font(.title2).bold()
                    Text("Private AI on this Mac").foregroundStyle(.secondary)
                }
            }
            switch installer.phase {
            case .idle:
                if installer.installed { installedView } else { welcomeView }
            case .running:
                runningView
            case .finished:
                finishedView
            case let .failed(message):
                failedView(message)
            }
        }
        .padding(24)
        .fixedSize(horizontal: false, vertical: true)
    }

    private var welcomeView: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("This sets up StarFerret on this Mac: the Board, Control, LibreChat for chat, and n8n for automations, plus an AI model sized to this Mac's memory.")
            Text("Most of the time is the model download, 5 to 17 GB. No account and no password. Needs an Apple silicon Mac and about 30 GB free.")
                .foregroundStyle(.secondary)
            Button("Install") { installer.install() }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .keyboardShortcut(.defaultAction)
        }
    }

    private var installedView: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("StarFerret is installed on this Mac.")
            openButtons
            Button("Repair or reinstall") { installer.install() }
                .buttonStyle(.link)
        }
    }

    private var runningView: some View {
        VStack(alignment: .leading, spacing: 10) {
            if installer.action == .uninstall {
                Text("Removing StarFerret's services…").font(.headline)
                ProgressView().progressViewStyle(.linear)
            } else {
                Text(installer.stepIndex > 0 ? "Step \(installer.stepIndex) of \(installer.stepTotal)" : "Starting")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(installer.stepTitle.isEmpty ? "Getting ready" : installer.stepTitle)
                    .font(.headline)
                ProgressView(value: Double(max(installer.stepIndex - 1, 0)), total: Double(max(installer.stepTotal, 1)))
                if let percent = installer.downloadPercent {
                    ProgressView(value: Double(percent), total: 100) {
                        Text("Model download: \(percent)%")
                    } currentValueLabel: {
                        Text(installer.downloadDetail)
                    }
                }
                if !installer.lastNote.isEmpty {
                    Text(installer.lastNote)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Text("You can close this window. StarFerret keeps going from the menu bar.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var finishedView: some View {
        VStack(alignment: .leading, spacing: 12) {
            if installer.action == .uninstall {
                Text("StarFerret's services are removed. Your data and models were kept.")
                Button("Install again") { installer.install() }
                    .buttonStyle(.borderedProminent)
            } else {
                Text("StarFerret is running.").font(.headline)
                Text("Control is where you make your admin and look after the apps. Share the Board with your team.")
                    .foregroundStyle(.secondary)
                openButtons
            }
        }
    }

    private func failedView(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("The install stopped", systemImage: "exclamationmark.triangle.fill")
                .font(.headline)
                .foregroundStyle(.orange)
            Text(message).textSelection(.enabled)
            HStack {
                Button("Try again") { installer.install() }
                    .buttonStyle(.borderedProminent)
                Button("Show the log") { installer.showLog() }
            }
        }
    }

    private var openButtons: some View {
        HStack {
            Button("Open Control") { installer.open(installer.controlURL) }
                .buttonStyle(.borderedProminent)
            Button("Open the Board") { installer.open(installer.boardURL) }
        }
    }
}
