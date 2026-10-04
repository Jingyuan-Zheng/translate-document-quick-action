import AppKit
import SwiftUI
import Translation

// A resident text-only bridge: JSON lines in/out, while Apple's native UI
// handles permission and language downloads. PDF processing stays in pdf2zh.
@available(macOS 15.0, *)
@MainActor final class ApplePDFState: ObservableObject {
    let source: Locale.Language?
    let target: Locale.Language
    let configuration: TranslationSession.Configuration
    let requests: AsyncStream<String>
    let continuation: AsyncStream<String>.Continuation
    weak var window: NSWindow?

    init(source: String, target: String) {
        self.source = source == "auto" ? nil : Locale.Language(identifier: source)
        self.target = Locale.Language(identifier: target)
        if #available(macOS 26.4, *) {
            configuration = TranslationSession.Configuration(source: self.source, target: self.target, preferredStrategy: .lowLatency)
        } else {
            configuration = TranslationSession.Configuration(source: self.source, target: self.target)
        }
        let stream = AsyncStream<String>.makeStream()
        requests = stream.stream
        continuation = stream.continuation
    }

    func reply(_ value: [String: String]) {
        if let data = try? JSONSerialization.data(withJSONObject: value),
           let line = String(data: data, encoding: .utf8) {
            print(line)
            fflush(stdout)
        }
    }
}

@available(macOS 15.0, *)
struct ApplePDFView: View {
    @ObservedObject var state: ApplePDFState
    var body: some View {
        VStack(spacing: 12) {
            Text("Apple PDF Translation").font(.headline)
            Text("Preparing on-device translation. Allow the language download if prompted.")
                .multilineTextAlignment(.center)
            ProgressView()
        }
        .padding(24).frame(width: 390, height: 140)
        .translationTask(state.configuration) { session in
            do {
                try await session.prepareTranslation()
                state.window?.orderOut(nil)
                state.reply(["event": "ready"])
                for await text in state.requests {
                    do {
                        let response = try await session.translate(text)
                        state.reply(["text": response.targetText])
                    } catch {
                        state.reply(["error": error.localizedDescription])
                    }
                }
            } catch {
                state.reply(["error": error.localizedDescription])
                NSApp.terminate(nil)
            }
        }
    }
}

@available(macOS 15.0, *)
@MainActor final class ApplePDFDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var state: ApplePDFState!
    func applicationDidFinishLaunching(_ notification: Notification) {
        let args = CommandLine.arguments
        func option(_ name: String, fallback: String) -> String {
            guard let index = args.firstIndex(of: name), index + 1 < args.count else { return fallback }
            return args[index + 1]
        }
        state = ApplePDFState(source: option("--source", fallback: "en"), target: option("--target", fallback: "zh-Hans"))
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 438, height: 188),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Apple PDF Translation"
        window.delegate = self
        window.isReleasedWhenClosed = false
        state.window = window
        window.contentView = NSHostingView(rootView: ApplePDFView(state: state))
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        let continuation = state.continuation
        Thread.detachNewThread {
            while let line = readLine() {
                guard let data = line.data(using: .utf8),
                      let request = try? JSONSerialization.jsonObject(with: data) as? [String: String],
                      let text = request["text"] else { continue }
                continuation.yield(text)
            }
            continuation.finish()
            DispatchQueue.main.async { NSApp.terminate(nil) }
        }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        state.reply(["error": "Apple translation was cancelled."])
        NSApp.terminate(nil)
        return true
    }
}

if #available(macOS 15.0, *) {
    MainActor.assumeIsolated {
        let app = NSApplication.shared
        let delegate = ApplePDFDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }
} else {
    fputs("Apple translation requires macOS 15 or later.\n", stderr)
    exit(1)
}
