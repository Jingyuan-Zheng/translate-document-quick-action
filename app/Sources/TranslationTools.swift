import AppKit
import SwiftUI
import UniformTypeIdentifiers

enum ToolKind: String {
    case pdf
    case document
    case image
    case audio
    case resize
    case ocr
}

struct ToolConfig {
    let title: String
    let subtitle: String
    let actionTitle: String
    let allowedExtensions: [String]
    let workerScript: String
}

final class CenteredClipTextFieldCell: NSTextFieldCell {
    override func titleRect(forBounds rect: NSRect) -> NSRect {
        var titleFrame = super.titleRect(forBounds: rect)
        let titleSize = attributedStringValue.size()
        titleFrame.origin.x = rect.origin.x + max(0, (rect.width - min(titleSize.width, rect.width)) / 2)
        titleFrame.size.width = min(titleSize.width + 8, rect.width)
        return titleFrame
    }

    override func drawInterior(withFrame cellFrame: NSRect, in controlView: NSView) {
        super.drawInterior(withFrame: titleRect(forBounds: cellFrame), in: controlView)
    }
}

final class SegmentSelectionModel: ObservableObject {
    var onChange: ((Int) -> Void)?
    @Published var index: Int = 0 {
        didSet {
            if oldValue != index {
                onChange?(index)
            }
        }
    }
}

@available(macOS 26.0, *)
struct GlassSegmentedPickerView: View {
    let labels: [String]
    @ObservedObject var selection: SegmentSelectionModel

    var body: some View {
        HStack(spacing: 8) {
            ForEach(labels.indices, id: \.self) { index in
                if selection.index == index {
                    Button(labels[index]) {
                        selection.index = index
                    }
                    .buttonStyle(.glassProminent)
                    .buttonBorderShape(.capsule)
                } else {
                    Button(labels[index]) {
                        selection.index = index
                    }
                    .buttonStyle(.glass)
                    .buttonBorderShape(.capsule)
                }
            }
        }
        .padding(2)
        .frame(maxWidth: .infinity, alignment: .center)
    }
}

final class SegmentedOptionControl: NSView {
    let items: [(String, String)]
    private let selection = SegmentSelectionModel()
    private var fallbackControl: NSSegmentedControl?
    var onSelectionChanged: ((SegmentedOptionControl) -> Void)?

    var selectedIndex: Int {
        get {
            fallbackControl?.selectedSegment ?? selection.index
        }
        set {
            let boundedIndex = min(max(newValue, 0), max(items.count - 1, 0))
            fallbackControl?.selectedSegment = boundedIndex
            selection.index = boundedIndex
        }
    }

    var selectedValue: String {
        guard selectedIndex >= 0, selectedIndex < items.count else { return "" }
        return items[selectedIndex].1
    }

    init(items: [(String, String)]) {
        self.items = items
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        setContentHuggingPriority(.defaultLow, for: .horizontal)
        setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        selection.onChange = { [weak self] _ in
            guard let self else { return }
            self.fallbackControl?.selectedSegment = self.selectedIndex
            self.onSelectionChanged?(self)
        }

        if #available(macOS 26.0, *) {
            let host = NSHostingView(rootView: GlassSegmentedPickerView(labels: items.map(\.0), selection: selection))
            host.translatesAutoresizingMaskIntoConstraints = false
            addSubview(host)
            NSLayoutConstraint.activate([
                host.topAnchor.constraint(equalTo: topAnchor),
                host.leadingAnchor.constraint(equalTo: leadingAnchor),
                host.trailingAnchor.constraint(equalTo: trailingAnchor),
                host.bottomAnchor.constraint(equalTo: bottomAnchor),
                heightAnchor.constraint(greaterThanOrEqualToConstant: 36)
            ])
        } else {
            let control = NSSegmentedControl(labels: items.map(\.0), trackingMode: .selectOne, target: self, action: #selector(fallbackSelectionChanged(_:)))
            control.segmentStyle = .rounded
            control.controlSize = .large
            control.selectedSegment = 0
            control.segmentDistribution = .fillEqually
            control.translatesAutoresizingMaskIntoConstraints = false
            addSubview(control)
            fallbackControl = control
            NSLayoutConstraint.activate([
                control.topAnchor.constraint(equalTo: topAnchor),
                control.leadingAnchor.constraint(equalTo: leadingAnchor),
                control.trailingAnchor.constraint(equalTo: trailingAnchor),
                control.bottomAnchor.constraint(equalTo: bottomAnchor)
            ])
        }
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc private func fallbackSelectionChanged(_ sender: NSSegmentedControl) {
        selection.index = sender.selectedSegment
    }
}

final class TranslationToolsApp: NSObject, NSApplicationDelegate, NSWindowDelegate, NSTextFieldDelegate {
    private var window: NSWindow!
    private var fileField: NSTextField!
    private var logTextView: NSTextView!
    private var runButton: NSButton!
    private var progressIndicator: NSProgressIndicator!

    private var engineControl: SegmentedOptionControl!
    private var targetQuickControl: SegmentedOptionControl!
    private var targetLanguagePopup: NSPopUpButton!
    private var modeControl: SegmentedOptionControl!
    private var sourceControl: SegmentedOptionControl!
    private var imageEngineControl: SegmentedOptionControl!
    private var textEngineControl: SegmentedOptionControl!
    private var backendControl: SegmentedOptionControl!
    private var operationControl: SegmentedOptionControl!
    private var resizeOperationControl: SegmentedOptionControl!
    private var resizeModeControl: SegmentedOptionControl!
    private var outputFormatPopup: NSPopUpButton!
    private var modelField: NSTextField!
    private var percentageSlider: NSSlider!
    private var percentageField: NSTextField!
    private var qualitySlider: NSSlider!
    private var qualityField: NSTextField!
    private var resizeQualityValue = 92
    private var compressQualityValue = 85
    private var widthField: NSTextField!
    private var heightField: NSTextField!
    private var useGPUCheck: NSButton!
    private var streamCheck: NSButton!
    private var preserveAspectCheck: NSButton!
    private var originalImageSize: NSSize?
    private var isUpdatingResizeFields = false

    private var tool: ToolKind = .pdf
    private var files: [String] = []
    private var process: Process?
    private var logBuffer: [String] = []
    private var standaloneAlertHostWindow: NSWindow?

    private var supportDir: String {
        Bundle.main.bundleURL.deletingLastPathComponent().path
    }
    private let extendedTargetLanguages: [(String, String)] = [
        ("Japanese", "ja"),
        ("Korean", "ko"),
        ("German", "de"),
        ("French", "fr"),
        ("Spanish", "es"),
        ("Italian", "it"),
        ("Portuguese", "pt"),
        ("Russian", "ru"),
    ]
    private var workersDir: String { "\(supportDir)/Workers" }
    private var config: ToolConfig {
        switch tool {
        case .pdf:
            return ToolConfig(
                title: "Translate PDF",
                subtitle: "Translate PDF files and save translated copies next to the originals.",
                actionTitle: "Translate",
                allowedExtensions: ["pdf"],
                workerScript: "\(workersDir)/translation_pdf_worker.py"
            )
        case .document:
            return ToolConfig(
                title: "Translate Document",
                subtitle: "Translate text, Markdown, and Word documents while preserving layout where possible.",
                actionTitle: "Translate",
                allowedExtensions: ["txt", "md", "markdown", "docx"],
                workerScript: "\(workersDir)/translate_document_worker.py"
            )
        case .image:
            return ToolConfig(
                title: "Translate Image",
                subtitle: "Extract and translate text from image files.",
                actionTitle: "Translate",
                allowedExtensions: ["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"],
                workerScript: "\(workersDir)/translate_image_worker.py"
            )
        case .audio:
            return ToolConfig(
                title: "Transcribe Audio",
                subtitle: "Transcribe audio or video, with optional translation output.",
                actionTitle: "Start",
                allowedExtensions: ["aac", "aif", "aiff", "flac", "m4a", "m4v", "mov", "mp3", "mp4", "wav"],
                workerScript: "\(workersDir)/translate_audio_worker.py"
            )
        case .resize:
            return ToolConfig(
                title: "Resize Image",
                subtitle: "Resize, optimize, and convert image files with ImageMagick.",
                actionTitle: "Resize",
                allowedExtensions: ["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "heic"],
                workerScript: "\(workersDir)/resize_image_worker.py"
            )
        case .ocr:
            return ToolConfig(
                title: "OCR",
                subtitle: "Create searchable PDF files from PDFs or images.",
                actionTitle: "Start OCR",
                allowedExtensions: ["pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp"],
                workerScript: "\(workersDir)/ocr_worker.py"
            )
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if CommandLine.arguments.contains("--preview-alert") {
            showStandaloneAlert(title: "Complete", message: "OCR completed.", style: .informational) {
                NSApp.terminate(nil)
            }
            return
        }

        parseArguments()
        if tool == .ocr {
            appendLog("Files received: \(files.isEmpty ? "none" : files.map { URL(fileURLWithPath: $0).lastPathComponent }.joined(separator: ", "))")
            runOCRSilently()
            return
        }

        buildWindow()
        updateFileField()
        updateResizeBaseline()
        appendLog("Files received: \(files.isEmpty ? "none" : files.map { URL(fileURLWithPath: $0).lastPathComponent }.joined(separator: ", "))")
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func parseArguments() {
        var iterator = CommandLine.arguments.dropFirst().makeIterator()
        var parsedFiles: [String] = []
        while let arg = iterator.next() {
            if arg == "--tool", let value = iterator.next(), let parsedTool = ToolKind(rawValue: value) {
                tool = parsedTool
            } else if arg == "--" {
                while let file = iterator.next() {
                    parsedFiles.append(file)
                }
            } else if !arg.hasPrefix("--") {
                parsedFiles.append(arg)
            }
        }
        let extensions = Set(config.allowedExtensions)
        files = parsedFiles.filter { extensions.contains(URL(fileURLWithPath: $0).pathExtension.lowercased()) }
    }

    private func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 820, height: 620),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.title = config.title
        window.minSize = NSSize(width: 720, height: 520)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.styleMask.insert(.fullSizeContentView)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.delegate = self

        let contentView = NSVisualEffectView(frame: window.contentView?.bounds ?? NSRect(x: 0, y: 0, width: 820, height: 620))
        contentView.material = .underWindowBackground
        contentView.blendingMode = .behindWindow
        contentView.state = .active
        contentView.autoresizingMask = [.width, .height]
        window.contentView = contentView

        let root = NSStackView()
        root.orientation = .vertical
        root.alignment = .width
        root.spacing = 16
        root.edgeInsets = NSEdgeInsets(top: 54, left: 20, bottom: 18, right: 20)
        root.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(root)

        let header = NSStackView()
        header.orientation = .horizontal
        header.alignment = .centerY
        header.spacing = 12
        let title = NSTextField(labelWithString: config.title)
        title.font = .systemFont(ofSize: 18, weight: .semibold)
        title.alignment = .left
        let subtitle = NSTextField(labelWithString: config.subtitle)
        subtitle.textColor = .secondaryLabelColor
        subtitle.font = .systemFont(ofSize: 12)
        subtitle.alignment = .left
        subtitle.lineBreakMode = .byTruncatingTail
        let titleStack = NSStackView(views: [title, subtitle])
        titleStack.orientation = .vertical
        titleStack.alignment = .leading
        titleStack.spacing = 1
        header.addArrangedSubview(titleStack)
        header.addArrangedSubview(spacer())
        root.addArrangedSubview(header)

        let optionsPanel = panel(material: .popover)
        let optionsFrame = NSView()
        optionsFrame.translatesAutoresizingMaskIntoConstraints = false
        optionsFrame.addSubview(optionsPanel)
        root.addArrangedSubview(optionsFrame)
        let optionsContent = panelContentView(optionsPanel)

        let form = NSGridView()
        form.rowSpacing = 10
        form.columnSpacing = 14
        form.translatesAutoresizingMaskIntoConstraints = false
        let formWrapper = NSView()
        formWrapper.translatesAutoresizingMaskIntoConstraints = false
        optionsContent.addSubview(formWrapper)
        formWrapper.addSubview(form)

        fileField = NSTextField(string: "")
        fileField.cell = CenteredClipTextFieldCell(textCell: "")
        fileField.isEditable = false
        fileField.alignment = .center
        fileField.lineBreakMode = .byTruncatingMiddle
        fileField.bezelStyle = .roundedBezel
        fileField.controlSize = .large
        let browseButton = button(title: "Browse", target: self, action: #selector(browseFiles(_:)), primary: false)
        let fileStack = NSStackView(views: [fileField, browseButton])
        fileStack.orientation = .horizontal
        fileStack.spacing = 8
        form.addRow(with: [label("Files"), fileStack])

        buildCommonOptionControls()
        addRows(to: form)

        let logPanel = panel(material: .underPageBackground, useGlass: false)
        root.addArrangedSubview(logPanel)
        let logContent = panelContentView(logPanel)

        let logScroll = NSScrollView()
        logScroll.borderType = .noBorder
        logScroll.hasVerticalScroller = true
        logScroll.drawsBackground = false
        logScroll.translatesAutoresizingMaskIntoConstraints = false
        logTextView = NSTextView()
        logTextView.isEditable = false
        logTextView.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        logTextView.textColor = .labelColor
        logTextView.backgroundColor = .clear
        logTextView.textContainerInset = NSSize(width: 12, height: 12)
        logScroll.documentView = logTextView
        logContent.addSubview(logScroll)

        let footer = NSStackView()
        footer.orientation = .horizontal
        footer.alignment = .centerY
        footer.spacing = 10
        progressIndicator = NSProgressIndicator()
        progressIndicator.style = .spinning
        progressIndicator.controlSize = .small
        progressIndicator.isDisplayedWhenStopped = false
        footer.addArrangedSubview(progressIndicator)
        footer.addArrangedSubview(spacer())
        let revealButton = button(title: "Reveal Folder", target: self, action: #selector(revealFirstFileFolder(_:)), primary: false)
        runButton = button(title: config.actionTitle, target: self, action: #selector(runTool(_:)), primary: true)
        footer.addArrangedSubview(revealButton)
        footer.addArrangedSubview(runButton)
        root.addArrangedSubview(footer)

        NSLayoutConstraint.activate([
            root.topAnchor.constraint(equalTo: contentView.topAnchor),
            root.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
            root.bottomAnchor.constraint(equalTo: contentView.bottomAnchor),
            optionsPanel.topAnchor.constraint(equalTo: optionsFrame.topAnchor),
            optionsPanel.centerXAnchor.constraint(equalTo: optionsFrame.centerXAnchor),
            optionsPanel.widthAnchor.constraint(lessThanOrEqualTo: optionsFrame.widthAnchor),
            optionsPanel.widthAnchor.constraint(lessThanOrEqualToConstant: 1100),
            optionsPanel.widthAnchor.constraint(greaterThanOrEqualToConstant: 620),
            optionsPanel.bottomAnchor.constraint(equalTo: optionsFrame.bottomAnchor),
            fileField.widthAnchor.constraint(greaterThanOrEqualToConstant: 440),
            formWrapper.topAnchor.constraint(equalTo: optionsContent.topAnchor, constant: 14),
            formWrapper.centerXAnchor.constraint(equalTo: optionsContent.centerXAnchor),
            formWrapper.widthAnchor.constraint(lessThanOrEqualTo: optionsContent.widthAnchor, constant: -28),
            formWrapper.widthAnchor.constraint(lessThanOrEqualToConstant: 760),
            formWrapper.widthAnchor.constraint(greaterThanOrEqualToConstant: 620),
            formWrapper.bottomAnchor.constraint(equalTo: optionsContent.bottomAnchor, constant: -14),
            form.topAnchor.constraint(equalTo: formWrapper.topAnchor),
            form.leadingAnchor.constraint(equalTo: formWrapper.leadingAnchor),
            form.trailingAnchor.constraint(equalTo: formWrapper.trailingAnchor),
            form.bottomAnchor.constraint(equalTo: formWrapper.bottomAnchor),
            logScroll.topAnchor.constraint(equalTo: logContent.topAnchor, constant: 1),
            logScroll.leadingAnchor.constraint(equalTo: logContent.leadingAnchor, constant: 1),
            logScroll.trailingAnchor.constraint(equalTo: logContent.trailingAnchor, constant: -1),
            logScroll.bottomAnchor.constraint(equalTo: logContent.bottomAnchor, constant: -1),
            logPanel.heightAnchor.constraint(greaterThanOrEqualToConstant: 230)
        ])
    }

    private func buildCommonOptionControls() {
        engineControl = segmented([
            ("Google", "google"),
            ("Bing", "bing"),
            ("Ollama", "ollama"),
        ])
        targetQuickControl = segmented([
            ("Chinese", "zh"),
            ("English", "en"),
        ])
        targetLanguagePopup = NSPopUpButton()
        targetLanguagePopup.controlSize = .large
        targetLanguagePopup.addItem(withTitle: "More Languages")
        targetLanguagePopup.lastItem?.representedObject = ""
        for (title, value) in extendedTargetLanguages {
            targetLanguagePopup.addItem(withTitle: title)
            targetLanguagePopup.lastItem?.representedObject = value
        }
        targetLanguagePopup.toolTip = "Choose another target language"
        targetLanguagePopup.setContentHuggingPriority(.defaultHigh, for: .horizontal)
        targetLanguagePopup.widthAnchor.constraint(greaterThanOrEqualToConstant: 168).isActive = true
        if #available(macOS 26.0, *) {
            targetLanguagePopup.bezelStyle = .glass
        }
        modeControl = segmented([
            ("Bilingual", "dual"),
            ("Monolingual", "mono"),
            ("Both", "both"),
        ])
        selectSegment(modeControl, value: tool == .audio ? "dual" : "both")
        sourceControl = segmented([
            ("Auto", "auto"),
            ("English", "en"),
            ("Japanese", "ja"),
            ("Chinese", "zh"),
        ])
        imageEngineControl = segmented([
            ("Simple macOS OCR", "simple-macos"),
            ("Manga Translator", "manga"),
        ])
        textEngineControl = segmented([
            ("Google", "google"),
            ("Bing", "bing"),
            ("Ollama", "ollama"),
        ])
        backendControl = segmented([
            ("Offline", "offline"),
            ("Custom OpenAI", "custom_openai"),
            ("ChatGPT", "chatgpt"),
            ("DeepL", "deepl"),
        ])
        operationControl = segmented([
            ("Transcribe only", "transcribe"),
            ("Transcribe + translate", "both"),
            ("Translate output only", "translate"),
        ])
        selectSegment(operationControl, value: "both")
        resizeOperationControl = segmented([
            ("Resize", "resize"),
            ("Compress", "optimize"),
        ])
        resizeModeControl = segmented([
            ("Percentage", "percentage"),
            ("Custom Size", "custom"),
        ])
        outputFormatPopup = NSPopUpButton()
        outputFormatPopup.controlSize = .large
        let formats: [(String, String)] = [
            ("Original Format", "original"),
            ("JPEG", "jpg"),
            ("PNG", "png"),
            ("WebP", "webp"),
            ("AVIF", "avif"),
            ("HEIC", "heic"),
            ("TIFF", "tiff"),
        ]
        for (title, value) in formats {
            outputFormatPopup.addItem(withTitle: title)
            outputFormatPopup.lastItem?.representedObject = value
        }
        outputFormatPopup.target = self
        outputFormatPopup.action = #selector(outputFormatChanged(_:))
        outputFormatPopup.setContentHuggingPriority(.defaultLow, for: .horizontal)
        outputFormatPopup.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        outputFormatPopup.widthAnchor.constraint(greaterThanOrEqualToConstant: 220).isActive = true
        if #available(macOS 26.0, *) {
            outputFormatPopup.bezelStyle = .glass
        }
        modelField = NSTextField(string: ProcessInfo.processInfo.environment["MACWHISPER_MODEL"] ?? "")
        modelField.bezelStyle = .roundedBezel
        modelField.controlSize = .large
        percentageSlider = NSSlider(value: 50, minValue: 1, maxValue: 200, target: self, action: #selector(percentageSliderChanged(_:)))
        percentageSlider.controlSize = .large
        percentageSlider.isContinuous = true
        percentageSlider.setContentHuggingPriority(.defaultLow, for: .horizontal)
        percentageSlider.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        percentageField = numberField("50")
        percentageField.target = self
        percentageField.action = #selector(percentageFieldChanged(_:))
        percentageField.delegate = self
        qualitySlider = NSSlider(value: Double(resizeQualityValue), minValue: 1, maxValue: 100, target: self, action: #selector(qualitySliderChanged(_:)))
        qualitySlider.controlSize = .large
        qualitySlider.isContinuous = true
        qualitySlider.setContentHuggingPriority(.defaultLow, for: .horizontal)
        qualitySlider.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        qualityField = numberField(String(resizeQualityValue))
        qualityField.target = self
        qualityField.action = #selector(qualityFieldChanged(_:))
        qualityField.delegate = self
        widthField = numberField("1024")
        widthField.target = self
        widthField.action = #selector(widthFieldChanged(_:))
        widthField.delegate = self
        heightField = numberField("1024")
        heightField.target = self
        heightField.action = #selector(heightFieldChanged(_:))
        heightField.delegate = self
        useGPUCheck = checkbox("Use GPU if available")
        streamCheck = checkbox("Stream transcript while transcribing")
        preserveAspectCheck = checkbox("Preserve aspect ratio")
        preserveAspectCheck.state = .on
        resizeOperationControl.onSelectionChanged = { [weak self] _ in
            self?.resizeOperationChanged()
        }
        updateQualityControlAvailability()
    }

    private func addRows(to form: NSGridView) {
        switch tool {
        case .pdf:
            engineControl = limitedSegmented(engineControl, allowedValues: ["google", "bing"])
            form.addRow(with: [label("Engine"), engineControl])
            form.addRow(with: [label("Target"), targetLanguageControl()])
            form.addRow(with: [label("Output"), modeControl])
        case .document:
            form.addRow(with: [label("Engine"), engineControl])
            form.addRow(with: [label("Target"), targetLanguageControl()])
            form.addRow(with: [label("Output"), modeControl])
        case .image:
            form.addRow(with: [label("Source"), sourceControl])
            form.addRow(with: [label("Target"), targetLanguageControl()])
            form.addRow(with: [label("Output"), modeControl])
            form.addRow(with: [label("Image Backend"), imageEngineControl])
            form.addRow(with: [label("Text Engine"), textEngineControl])
            form.addRow(with: [label("Manga Backend"), backendControl])
            form.addRow(with: [label(""), useGPUCheck])
        case .audio:
            form.addRow(with: [label("Action"), operationControl])
            form.addRow(with: [label("Text Engine"), engineControl])
            form.addRow(with: [label("Target"), targetLanguageControl()])
            form.addRow(with: [label("Output"), modeControl])
            form.addRow(with: [label("MacWhisper Model"), modelField])
            form.addRow(with: [label(""), streamCheck])
        case .resize:
            form.addRow(with: [label("Operation"), resizeOperationControl])
            form.addRow(with: [label("Mode"), resizeModeControl])
            form.addRow(with: [label("Percent"), percentageControl()])
            form.addRow(with: [label("Width"), widthField])
            form.addRow(with: [label("Height"), heightField])
            form.addRow(with: [label("Format"), outputFormatPopup])
            form.addRow(with: [label("Output Quality"), qualityControl()])
            form.addRow(with: [label(""), preserveAspectCheck])
        case .ocr:
            form.addRow(with: [label("Mode"), label("Force OCR and save next to the original file")])
        }
        form.column(at: 0).xPlacement = .trailing
        form.column(at: 1).xPlacement = .fill
    }

    private func limitedSegmented(_ source: SegmentedOptionControl, allowedValues: [String]) -> SegmentedOptionControl {
        let items = source.items.compactMap { item -> (String, String)? in
            let value = item.1
            guard allowedValues.contains(value) else { return nil }
            return item
        }
        return segmented(items)
    }

    private func targetLanguageControl() -> NSStackView {
        let stack = NSStackView(views: [targetQuickControl, targetLanguagePopup])
        stack.orientation = .horizontal
        stack.spacing = 10
        stack.alignment = .centerY
        targetQuickControl.setContentHuggingPriority(.defaultLow, for: .horizontal)
        targetLanguagePopup.setContentHuggingPriority(.defaultHigh, for: .horizontal)
        return stack
    }

    private func selectedTargetLanguage() -> String {
        if let value = targetLanguagePopup.selectedItem?.representedObject as? String, !value.isEmpty {
            return value
        }
        return selectedValue(targetQuickControl)
    }

    private func label(_ text: String) -> NSTextField {
        let field = NSTextField(labelWithString: text)
        field.textColor = .secondaryLabelColor
        field.alignment = .right
        return field
    }

    private func segmented(_ items: [(String, String)]) -> SegmentedOptionControl {
        SegmentedOptionControl(items: items)
    }

    private func selectSegment(_ control: SegmentedOptionControl, value: String) {
        guard let index = control.items.firstIndex(where: { $0.1 == value }) else { return }
        control.selectedIndex = index
    }

    private func panel(material: NSVisualEffectView.Material, useGlass: Bool = true) -> NSView {
        if #available(macOS 26.0, *), useGlass {
            let view = NSGlassEffectView()
            view.style = .regular
            view.cornerRadius = 16
            view.tintColor = NSColor.windowBackgroundColor.withAlphaComponent(0.18)
            view.contentView = NSView()
            view.translatesAutoresizingMaskIntoConstraints = false
            return view
        }

        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = .withinWindow
        view.state = .active
        view.translatesAutoresizingMaskIntoConstraints = false
        view.wantsLayer = true
        view.layer?.cornerRadius = 12
        view.layer?.masksToBounds = true
        return view
    }

    private func panelContentView(_ panel: NSView) -> NSView {
        if #available(macOS 26.0, *), let glass = panel as? NSGlassEffectView, let content = glass.contentView {
            return content
        }
        return panel
    }

    private func button(title: String, target: AnyObject?, action: Selector, primary: Bool) -> NSButton {
        let button = NSButton(title: title, target: target, action: action)
        button.controlSize = .large
        if #available(macOS 26.0, *) {
            button.bezelStyle = .glass
            button.borderShape = .capsule
            if primary {
                button.bezelColor = .controlAccentColor
            }
        } else {
            button.bezelStyle = .rounded
            if primary {
                button.bezelColor = .controlAccentColor
            }
        }
        return button
    }

    private func checkbox(_ title: String) -> NSButton {
        NSButton(checkboxWithTitle: title, target: nil, action: nil)
    }

    private func numberField(_ value: String) -> NSTextField {
        let field = NSTextField(string: value)
        field.bezelStyle = .roundedBezel
        field.controlSize = .large
        field.alignment = .center
        return field
    }

    private func percentageControl() -> NSStackView {
        let suffix = NSTextField(labelWithString: "%")
        suffix.textColor = .secondaryLabelColor
        percentageField.widthAnchor.constraint(equalToConstant: 64).isActive = true
        percentageSlider.widthAnchor.constraint(greaterThanOrEqualToConstant: 260).isActive = true

        let stack = NSStackView(views: [percentageSlider, percentageField, suffix])
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 8
        stack.distribution = .fill
        stack.setContentHuggingPriority(.defaultLow, for: .horizontal)
        stack.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return stack
    }

    private func qualityControl() -> NSStackView {
        let suffix = NSTextField(labelWithString: "%")
        suffix.textColor = .secondaryLabelColor
        qualityField.widthAnchor.constraint(equalToConstant: 64).isActive = true
        qualitySlider.widthAnchor.constraint(greaterThanOrEqualToConstant: 260).isActive = true

        let stack = NSStackView(views: [qualitySlider, qualityField, suffix])
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 8
        stack.distribution = .fill
        stack.setContentHuggingPriority(.defaultLow, for: .horizontal)
        stack.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return stack
    }

    @objc private func percentageSliderChanged(_ sender: NSSlider) {
        percentageField.stringValue = String(Int(sender.doubleValue.rounded()))
        updateResizeFieldsFromPercentage()
    }

    @objc private func qualitySliderChanged(_ sender: NSSlider) {
        let value = Int(sender.doubleValue.rounded())
        qualityField.stringValue = String(value)
        storeQualityValue(value)
    }

    @objc private func percentageFieldChanged(_ sender: NSTextField) {
        updatePercentageFromTextField(commit: true)
    }

    @objc private func qualityFieldChanged(_ sender: NSTextField) {
        updateQualityFromTextField(commit: true)
    }

    @objc private func outputFormatChanged(_ sender: NSPopUpButton) {
        updateQualityControlAvailability()
    }

    private func resizeOperationChanged() {
        let value = qualityValue(for: selectedValue(resizeOperationControl))
        setQualityControlValue(value)
        updateQualityControlAvailability()
    }

    @objc private func widthFieldChanged(_ sender: NSTextField) {
        updateResizeFieldsFromCustomSize(changedWidth: true)
    }

    @objc private func heightFieldChanged(_ sender: NSTextField) {
        updateResizeFieldsFromCustomSize(changedWidth: false)
    }

    private func updatePercentageFromTextField(commit: Bool = false) {
        let text = percentageField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsedValue = Double(text) else { return }
        let value = min(max(parsedValue, percentageSlider.minValue), percentageSlider.maxValue)
        percentageSlider.doubleValue = value
        if commit {
            percentageField.stringValue = String(Int(value.rounded()))
        }
        updateResizeFieldsFromPercentage()
    }

    private func updateQualityFromTextField(commit: Bool = false) {
        let text = qualityField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsedValue = Double(text) else { return }
        let value = min(max(parsedValue, qualitySlider.minValue), qualitySlider.maxValue)
        qualitySlider.doubleValue = value
        if commit {
            qualityField.stringValue = String(Int(value.rounded()))
        }
        storeQualityValue(Int(value.rounded()))
    }

    private func updateQualityControlAvailability() {
        guard qualitySlider != nil, qualityField != nil, outputFormatPopup != nil else { return }
        let value = selectedOutputFormat()
        let supportsQuality = ["original", "jpg", "jpeg", "webp", "avif", "heic"].contains(value)
        qualitySlider.isEnabled = supportsQuality
        qualityField.isEnabled = supportsQuality
    }

    private func qualityValue(for operation: String) -> Int {
        operation == "optimize" ? compressQualityValue : resizeQualityValue
    }

    private func storeQualityValue(_ value: Int) {
        if selectedValue(resizeOperationControl) == "optimize" {
            compressQualityValue = value
        } else {
            resizeQualityValue = value
        }
    }

    private func setQualityControlValue(_ value: Int) {
        qualitySlider.doubleValue = Double(value)
        qualityField.stringValue = String(value)
    }

    func controlTextDidChange(_ notification: Notification) {
        guard let field = notification.object as? NSTextField else { return }
        if field === percentageField {
            updatePercentageFromTextField()
        } else if field === qualityField {
            updateQualityFromTextField()
        } else if field === widthField {
            updateResizeFieldsFromCustomSize(changedWidth: true)
        } else if field === heightField {
            updateResizeFieldsFromCustomSize(changedWidth: false)
        }
    }

    private func spacer() -> NSView {
        let view = NSView()
        view.setContentHuggingPriority(.defaultLow, for: .horizontal)
        return view
    }

    @objc private func browseFiles(_ sender: Any?) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        let contentTypes = config.allowedExtensions.compactMap { UTType(filenameExtension: $0) }
        if !contentTypes.isEmpty {
            panel.allowedContentTypes = contentTypes
        }
        if panel.runModal() == .OK {
            files = panel.urls.map(\.path)
            updateFileField()
            updateResizeBaseline()
            appendLog("Files selected: \(files.map { URL(fileURLWithPath: $0).lastPathComponent }.joined(separator: ", "))")
        }
    }

    @objc private func revealFirstFileFolder(_ sender: Any?) {
        guard let first = files.first else { return }
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: first)])
    }

    @objc private func runTool(_ sender: Any?) {
        guard !files.isEmpty else {
            showAlert(title: "No Files", message: "Select at least one supported file.")
            return
        }
        guard FileManager.default.fileExists(atPath: config.workerScript) else {
            showAlert(title: "Missing Worker", message: config.workerScript)
            return
        }
        runButton.isEnabled = false
        progressIndicator.startAnimation(nil)
        appendLog("\nStarting \(config.title)...")

        let python = pythonPath()
        let command = buildCommand(python: python)
        appendLog("Running command: \(command.map { shellQuote($0) }.joined(separator: " "))")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = Array(command.dropFirst())
        process.environment = ProcessInfo.processInfo.environment
        self.process = process

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                self?.appendLog(text.trimmingCharacters(in: .newlines))
            }
        }
        process.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                pipe.fileHandleForReading.readabilityHandler = nil
                self?.runButton.isEnabled = true
                self?.progressIndicator.stopAnimation(nil)
                let ok = process.terminationStatus == 0
                self?.appendLog(ok ? "\nCompleted." : "\nFailed with exit code \(process.terminationStatus).")
                self?.showAlert(title: ok ? "Complete" : "Failed", message: ok ? "\(self?.config.title ?? "Task") completed." : "See log for details.")
            }
        }
        do {
            try process.run()
        } catch {
            runButton.isEnabled = true
            progressIndicator.stopAnimation(nil)
            showAlert(title: "Could Not Start", message: error.localizedDescription)
        }
    }

    private func runOCRSilently() {
        guard !files.isEmpty else {
            showOCRFailureWindow(title: "No Files", message: "Select at least one supported file.")
            return
        }
        guard FileManager.default.fileExists(atPath: config.workerScript) else {
            showOCRFailureWindow(title: "Missing Worker", message: config.workerScript)
            return
        }

        appendLog("\nStarting \(config.title)...")
        let python = pythonPath()
        let command = buildCommand(python: python)
        appendLog("Running command: \(command.map { shellQuote($0) }.joined(separator: " "))")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = Array(command.dropFirst())
        process.environment = ProcessInfo.processInfo.environment
        self.process = process

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                self?.appendLog(text.trimmingCharacters(in: .newlines))
            }
        }

        process.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                pipe.fileHandleForReading.readabilityHandler = nil
                let ok = process.terminationStatus == 0
                self?.appendLog(ok ? "\nCompleted." : "\nFailed with exit code \(process.terminationStatus).")
                if ok {
                    self?.showStandaloneAlert(title: "Complete", message: "OCR completed.", style: .informational) {
                        NSApp.terminate(nil)
                    }
                } else {
                    self?.showOCRFailureWindow(title: "Failed", message: "See log for details.")
                }
            }
        }

        do {
            try process.run()
        } catch {
            showOCRFailureWindow(title: "Could Not Start", message: error.localizedDescription)
        }
    }

    private func showOCRFailureWindow(title: String, message: String) {
        if window == nil {
            buildWindow()
            updateFileField()
            updateResizeBaseline()
            restoreBufferedLog()
            window.makeKeyAndOrderFront(nil)
            window.orderFrontRegardless()
            NSApp.activate(ignoringOtherApps: true)
        }
        runButton?.isEnabled = true
        progressIndicator?.stopAnimation(nil)
        showAlert(title: title, message: message)
    }

    private func buildCommand(python: String) -> [String] {
        var command = [python, config.workerScript]
        switch tool {
        case .pdf, .document:
            command += ["--engine", selectedValue(engineControl)]
            command += ["--lang-out", selectedTargetLanguage()]
            command += ["--mode", selectedValue(modeControl)]
        case .image:
            command += ["--lang-in", selectedValue(sourceControl)]
            command += ["--lang-out", selectedTargetLanguage()]
            command += ["--mode", selectedValue(modeControl)]
            command += ["--image-engine", selectedValue(imageEngineControl)]
            command += ["--text-engine", selectedValue(textEngineControl)]
            command += ["--mit-translator", selectedValue(backendControl)]
            if useGPUCheck.state == .on {
                command.append("--use-gpu")
            }
        case .audio:
            command += ["--operation", selectedValue(operationControl)]
            command += ["--engine", selectedValue(engineControl)]
            command += ["--lang-out", selectedTargetLanguage()]
            command += ["--mode", selectedValue(modeControl)]
            let model = modelField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            if !model.isEmpty {
                command += ["--model", model]
            }
            if streamCheck.state == .on {
                command.append("--stream")
            }
        case .resize:
            command += ["--operation", selectedValue(resizeOperationControl)]
            command += ["--mode", selectedValue(resizeModeControl)]
            command += ["--percentage", String(Int(percentageSlider.doubleValue.rounded()))]
            command += ["--width", widthField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)]
            command += ["--height", heightField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)]
            command += ["--format", selectedOutputFormat()]
            command += ["--quality", String(Int(qualitySlider.doubleValue.rounded()))]
            if preserveAspectCheck.state == .on {
                command.append("--preserve-aspect")
            }
        case .ocr:
            break
        }
        command += files
        return command
    }

    private func selectedValue(_ control: SegmentedOptionControl) -> String {
        control.selectedValue
    }

    private func selectedOutputFormat() -> String {
        if let value = outputFormatPopup.selectedItem?.representedObject as? String, !value.isEmpty {
            return value
        }
        return "original"
    }

    private func pythonPath() -> String {
        let candidates = [
            ProcessInfo.processInfo.environment["TRANSLATION_TOOLS_PYTHON"],
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]
        for candidate in candidates {
            if let path = candidate, FileManager.default.isExecutableFile(atPath: path) {
                return path
            }
        }
        return "/usr/bin/python3"
    }

    private func updateFileField() {
        fileField.stringValue = files.isEmpty ? "" : files.joined(separator: "; ")
        fileField.toolTip = fileField.stringValue
    }

    private func updateResizeBaseline() {
        guard tool == .resize else { return }
        originalImageSize = files.first.flatMap { imagePixelSize(path: $0) }
        updateResizeFieldsFromPercentage()
    }

    private func imagePixelSize(path: String) -> NSSize? {
        guard let image = NSImage(contentsOfFile: path) else { return nil }
        if let representation = image.representations.max(by: { $0.pixelsWide * $0.pixelsHigh < $1.pixelsWide * $1.pixelsHigh }),
           representation.pixelsWide > 0,
           representation.pixelsHigh > 0 {
            return NSSize(width: representation.pixelsWide, height: representation.pixelsHigh)
        }
        return image.size.width > 0 && image.size.height > 0 ? image.size : nil
    }

    private func updateResizeFieldsFromPercentage() {
        guard tool == .resize, !isUpdatingResizeFields, let size = originalImageSize else { return }
        isUpdatingResizeFields = true
        let scale = percentageSlider.doubleValue / 100
        widthField.stringValue = String(max(1, Int((size.width * scale).rounded())))
        heightField.stringValue = String(max(1, Int((size.height * scale).rounded())))
        isUpdatingResizeFields = false
    }

    private func updateResizeFieldsFromCustomSize(changedWidth: Bool) {
        guard tool == .resize, !isUpdatingResizeFields, preserveAspectCheck.state == .on, let size = originalImageSize else { return }
        isUpdatingResizeFields = true
        if changedWidth {
            let width = max(1, widthField.integerValue)
            let height = max(1, Int((Double(width) * size.height / size.width).rounded()))
            heightField.stringValue = String(height)
        } else {
            let height = max(1, heightField.integerValue)
            let width = max(1, Int((Double(height) * size.width / size.height).rounded()))
            widthField.stringValue = String(width)
        }
        isUpdatingResizeFields = false
    }

    private func appendLog(_ message: String) {
        guard !message.isEmpty else { return }
        logBuffer.append(message)
        guard logTextView != nil else { return }
        let text = logTextView.string
        logTextView.string = text.isEmpty ? message : text + "\n" + message
        logTextView.scrollToEndOfDocument(nil)
    }

    private func restoreBufferedLog() {
        guard logTextView != nil else { return }
        logTextView.string = logBuffer.joined(separator: "\n")
        logTextView.scrollToEndOfDocument(nil)
    }

    private func shellQuote(_ value: String) -> String {
        if value.rangeOfCharacter(from: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "\"'"))) == nil {
            return value
        }
        return "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    private func showAlert(title: String, message: String) {
        let isSuccess = title == "Complete"
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = isSuccess ? .informational : .warning
        alert.addButton(withTitle: "OK")

        if let window {
            alert.beginSheetModal(for: window)
        } else {
            alert.runModal()
        }
    }

    private func showStandaloneAlert(
        title: String,
        message: String,
        style: NSAlert.Style,
        completion: (() -> Void)? = nil
    ) {
        let hostWindow = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 320),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )
        hostWindow.center()
        hostWindow.titleVisibility = .hidden
        hostWindow.titlebarAppearsTransparent = true
        hostWindow.styleMask.insert(.fullSizeContentView)
        hostWindow.isOpaque = false
        hostWindow.backgroundColor = .clear
        hostWindow.alphaValue = 0.01
        hostWindow.level = .modalPanel
        standaloneAlertHostWindow = hostWindow

        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = style
        alert.addButton(withTitle: "OK")
        NSApp.activate(ignoringOtherApps: true)
        hostWindow.makeKeyAndOrderFront(nil)
        alert.beginSheetModal(for: hostWindow) { [weak self] _ in
            self?.standaloneAlertHostWindow?.close()
            self?.standaloneAlertHostWindow = nil
            completion?()
        }
    }
}

let app = NSApplication.shared
let delegate = TranslationToolsApp()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
