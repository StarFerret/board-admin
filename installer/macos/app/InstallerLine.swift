import Foundation

/// One line of output from install-starferret.sh, understood.
///
/// The app shows the installer's own words, so the window and the Terminal
/// install always say the same thing. Keep these patterns in step with the
/// `step`, `ok`, `die`, and download progress lines in install-starferret.sh.
enum InstallerLine: Equatable {
    /// `[4/9] Starting Board and Control`
    case step(index: Int, total: Int, title: String)
    /// `      Downloading qwen3.8:27b: 34% (5.8 of 17.0 GB)`
    case download(model: String, percent: Int, detail: String)
    /// `Install stopped. <what failed and what to do>`
    case stopped(message: String)
    /// `      ✓ Board and Control are running`
    case done(message: String)
    /// `      ! Under 30GB of free disk...`
    case warning(message: String)
    /// Anything else worth keeping in the log.
    case other(text: String)
    /// Blank lines.
    case blank
}

private let stepPattern = try! NSRegularExpression(pattern: #"^\[(\d+)/(\d+)\] (.+)$"#)
private let downloadPattern = try! NSRegularExpression(pattern: #"^Downloading (.+): (\d+)% \((.+)\)$"#)

private func groups(_ regex: NSRegularExpression, _ text: String) -> [String]? {
    let range = NSRange(text.startIndex..., in: text)
    guard let match = regex.firstMatch(in: text, range: range) else { return nil }
    return (1..<match.numberOfRanges).map { index in
        guard let r = Range(match.range(at: index), in: text) else { return "" }
        return String(text[r])
    }
}

func parseInstallerLine(_ raw: String) -> InstallerLine {
    // Strip colour codes and the carriage return a terminal progress line would use.
    let noColor = raw.replacingOccurrences(of: #"\x{1B}\[[0-9;]*[A-Za-z]"#, with: "", options: .regularExpression)
    let text = noColor.replacingOccurrences(of: "\r", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty { return .blank }

    if let g = groups(stepPattern, text), let index = Int(g[0]), let total = Int(g[1]) {
        return .step(index: index, total: total, title: g[2])
    }
    if let g = groups(downloadPattern, text), let percent = Int(g[1]) {
        return .download(model: g[0], percent: percent, detail: g[2])
    }
    if text.hasPrefix("Install stopped.") {
        let message = text.dropFirst("Install stopped.".count).trimmingCharacters(in: .whitespaces)
        return .stopped(message: message.isEmpty ? "The installer stopped." : message)
    }
    if text.hasPrefix("✓ ") { return .done(message: String(text.dropFirst(2))) }
    if text.hasPrefix("! ") { return .warning(message: String(text.dropFirst(2))) }
    return .other(text: text)
}
