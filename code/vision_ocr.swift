import Foundation
import ImageIO
import Vision

let paths = Array(CommandLine.arguments.dropFirst())
var results: [String: String] = [:]
for path in paths {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        results[path] = ""
        continue
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    do {
        try VNImageRequestHandler(cgImage: cgImage).perform([request])
        results[path] = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
    } catch {
        fputs("OCR error for \(path): \(error)\n", stderr)
        results[path] = ""
    }
}
let data = try JSONSerialization.data(withJSONObject: results, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
