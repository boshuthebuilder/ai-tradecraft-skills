// render: makes the fixture's scanned images and PDFs on macOS (used once by build.py; the outputs are committed).
//   render image <out.png> <text>          text drawn as pixels on a white page (a "scan", no text layer)
//   render textpdf <out.pdf> <text>        a one-page PDF with a real text layer
//   render imagepdf <out.pdf> <img>...     an image-only PDF, one page per image
//   render merge <out.pdf> <in.pdf>...     pages of several PDFs in order
import AppKit
import PDFKit

let args = CommandLine.arguments
let page = NSSize(width: 612, height: 792)

func attributed(_ text: String, size: CGFloat) -> NSAttributedString {
    let style = NSMutableParagraphStyle()
    style.lineSpacing = 6
    return NSAttributedString(string: text, attributes: [
        .font: NSFont(name: "PingFang SC", size: size) ?? NSFont.systemFont(ofSize: size),
        .foregroundColor: NSColor.black, .paragraphStyle: style])
}

func image(_ out: String, _ text: String) {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1224, pixelsHigh: 1584, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    NSColor.white.setFill()
    NSRect(x: 0, y: 0, width: 1224, height: 1584).fill()
    attributed(text, size: 34).draw(in: NSRect(x: 90, y: 90, width: 1044, height: 1400))
    NSGraphicsContext.restoreGraphicsState()
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
}

func textpdf(_ out: String, _ text: String) {
    var box = CGRect(origin: .zero, size: page)
    let ctx = CGContext(URL(fileURLWithPath: out) as CFURL, mediaBox: &box, nil)!
    ctx.beginPDFPage(nil)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: false)
    attributed(text, size: 12).draw(in: NSRect(x: 54, y: 54, width: 504, height: 684))
    NSGraphicsContext.restoreGraphicsState()
    ctx.endPDFPage()
    ctx.closePDF()
}

func imagepdf(_ out: String, _ imgs: [String]) {
    let doc = PDFDocument()
    for (i, p) in imgs.enumerated() {
        doc.insert(PDFPage(image: NSImage(contentsOfFile: p)!)!, at: i)
    }
    doc.write(to: URL(fileURLWithPath: out))
}

func merge(_ out: String, _ ins: [String]) {
    let doc = PDFDocument()
    for p in ins {
        let d = PDFDocument(url: URL(fileURLWithPath: p))!
        for i in 0..<d.pageCount { doc.insert(d.page(at: i)!, at: doc.pageCount) }
    }
    doc.write(to: URL(fileURLWithPath: out))
}

switch args[1] {
case "image": image(args[2], args[3])
case "textpdf": textpdf(args[2], args[3])
case "imagepdf": imagepdf(args[2], Array(args[3...]))
case "merge": merge(args[2], Array(args[3...]))
default: fatalError("unknown command")
}
