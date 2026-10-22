// 이미지에서 글자를 찾는다(맥 내장 Vision). 사용: swift ocr.swift a.png b.png …  → 줄마다 "파일\t글자\t신뢰도"
import Foundation
import Vision
import AppKit
for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["ko-KR", "en-US"]
    req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    for o in (req.results ?? []) {
        if let c = o.topCandidates(1).first {
            print("\(path)\t\(c.string)\t\(String(format: "%.2f", c.confidence))")
        }
    }
}
