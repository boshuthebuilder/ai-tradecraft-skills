// page-ocr: Apple Vision text recognition for the pre-onboarding extraction tool.
// Build: swiftc -O page_ocr.swift -o page-ocr   (macOS 13+)
// Usage:
//   page-ocr [--lang zh-Hans,en-US] image [image ...]   one JSON line per image
//   page-ocr --stdin [--lang ...]                       read image paths (one per line) from stdin
// Each line: {"file", "text", "confidence" (mean of top candidates, 0-1), "lines", "error"?}
// A line of the form "LANG=<codes>|<path>" on stdin overrides the languages for that image.
import AppKit
import Foundation
import Vision

func emit(_ obj: [String: Any]) {
    if let d = try? JSONSerialization.data(withJSONObject: obj),
       let s = String(data: d, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}

func recognise(_ path: String, _ langs: [String]?) -> [String: Any] {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return ["file": path, "text": "", "confidence": 0, "lines": 0, "error": "unreadable image"]
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    if let l = langs, !l.isEmpty {
        req.recognitionLanguages = l
    } else if #available(macOS 13.0, *) {
        req.automaticallyDetectsLanguage = true
    }
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try handler.perform([req])
    } catch {
        return ["file": path, "text": "", "confidence": 0, "lines": 0, "error": "\(error)"]
    }
    var lines: [String] = []
    var confs: [Float] = []
    for o in req.results ?? [] {
        if let c = o.topCandidates(1).first {
            lines.append(c.string)
            confs.append(c.confidence)
        }
    }
    let mean = confs.isEmpty ? 0 : confs.reduce(0, +) / Float(confs.count)
    return ["file": path, "text": lines.joined(separator: "\n"), "confidence": Double(mean), "lines": lines.count]
}

var args = Array(CommandLine.arguments.dropFirst())
var langs: [String]? = nil
var useStdin = false
var files: [String] = []
var i = 0
while i < args.count {
    let a = args[i]
    if a == "--lang", i + 1 < args.count {
        langs = args[i + 1].split(separator: ",").map { String($0) }
        i += 2
        continue
    }
    if a == "--stdin" { useStdin = true; i += 1; continue }
    files.append(a)
    i += 1
}

if useStdin {
    while let line = readLine() {
        let t = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { continue }
        var p = t
        var l = langs
        if t.hasPrefix("LANG="), let bar = t.firstIndex(of: "|") {
            let codes = t[t.index(t.startIndex, offsetBy: 5)..<bar]
            l = codes.split(separator: ",").map { String($0) }
            p = String(t[t.index(after: bar)...])
        }
        autoreleasepool { emit(recognise(p, l)) }
    }
} else {
    for p in files {
        autoreleasepool { emit(recognise(p, langs)) }
    }
}
