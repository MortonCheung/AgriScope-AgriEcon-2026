import Foundation
import PDFKit
import Vision
import AppKit

// 用法: swift ocr_pdf.swift <input.pdf> <output.txt>
let args = CommandLine.arguments
guard args.count >= 3 else {
    print("usage: swift ocr_pdf.swift <input.pdf> <output.txt>")
    exit(1)
}
let pdfPath = args[1]
let outPath = args[2]

guard let doc = PDFDocument(url: URL(fileURLWithPath: pdfPath)) else {
    print("无法打开 PDF")
    exit(1)
}

let pageCount = doc.pageCount
print("页数: \(pageCount)")

var allText = ""
for i in 0..<pageCount {
    guard let page = doc.page(at: i) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let img = NSImage(size: bounds.size)
    img.lockFocus()
    NSColor.white.set()
    bounds.fill()
    page.draw(with: .mediaBox, to: NSGraphicsContext.current!.cgContext)
    img.unlockFocus()
    var rect = NSRect(origin: .zero, size: bounds.size)
    guard let cgImage = img.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { continue }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
        if let results = request.results {
            var pageText = ""
            for obs in results {
                if let top = obs.topCandidates(1).first {
                    pageText += top.string + "\n"
                }
            }
            allText += "===== 第\(i+1)页 =====\n" + pageText + "\n"
        }
    } catch {
        print("OCR 第\(i+1)页失败: \(error)")
    }
    print("已处理第 \(i+1)/\(pageCount) 页")
}

try! allText.write(toFile: outPath, atomically: true, encoding: .utf8)
print("完成 → \(outPath), 共 \(allText.count) 字符")
