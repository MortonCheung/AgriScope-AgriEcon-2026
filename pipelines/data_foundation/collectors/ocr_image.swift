import Foundation
import Vision
import AppKit

// 用法: swift ocr_image.swift <input.png> <output.txt>
// 使用 macOS Vision 框架做中文 OCR（accurate 级别）
let args = CommandLine.arguments
guard args.count >= 3 else {
    print("usage: swift ocr_image.swift <input.png> <output.txt>")
    exit(1)
}
let imgPath = args[1]
let outPath = args[2]

guard let img = NSImage(contentsOfFile: imgPath) else {
    print("无法打开图片")
    exit(1)
}
var rect = NSRect(origin: .zero, size: img.size)
guard let cg = img.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
    print("无法转换 CGImage")
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = false        // 数字表格关掉语言纠正，避免改数

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([request])
    guard let obs = request.results else { exit(0) }
    // 按纵坐标排序（自上而下），同一行内按横坐标
    let sorted = obs.sorted { a, b in
        let ay = a.boundingBox.origin.y, by = b.boundingBox.origin.y
        if abs(ay - by) > 0.012 { return ay > by }
        return a.boundingBox.origin.x < b.boundingBox.origin.x
    }
    var lines: [String] = []
    var curY: CGFloat = -1
    var cur: [String] = []
    for o in sorted {
        guard let top = o.topCandidates(1).first else { continue }
        let y = o.boundingBox.origin.y
        if curY < 0 || abs(y - curY) <= 0.012 {
            cur.append(top.string)
            if curY < 0 { curY = y }
        } else {
            lines.append(cur.joined(separator: "\t"))
            cur = [top.string]
            curY = y
        }
    }
    if !cur.isEmpty { lines.append(cur.joined(separator: "\t")) }
    try lines.joined(separator: "\n").write(toFile: outPath, atomically: true, encoding: .utf8)
    print("识别 \(obs.count) 个文本块 -> \(lines.count) 行")
} catch {
    print("OCR 失败: \(error)")
    exit(1)
}
