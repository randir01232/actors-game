// usage: facecrop <inDir> <outDir>  -> writes crops as JPEG + prints JSON lines {file, quality, faceH}
import Foundation
import Vision
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
let inDir = URL(fileURLWithPath: args[1]), outDir = URL(fileURLWithPath: args[2])
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
let outSize = 420

let files = (try FileManager.default.contentsOfDirectory(atPath: inDir.path)).filter { $0.hasSuffix(".jpg") || $0.hasSuffix(".png") }.sorted()
for f in files {
    let url = inDir.appendingPathComponent(f)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let img0 = CGImageSourceCreateImageAtIndex(src, 0, [kCGImageSourceShouldCache: true] as CFDictionary) else { continue }
    // respect EXIF orientation by rendering via thumbnail API
    let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                                 kCGImageSourceThumbnailMaxPixelSize: max(img0.width, img0.height)]
    let img = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) ?? img0
    let W = CGFloat(img.width), H = CGFloat(img.height)
    let handler = VNImageRequestHandler(cgImage: img, options: [:])
    let q = VNDetectFaceCaptureQualityRequest()
    let lm = VNDetectFaceLandmarksRequest()
    do { try handler.perform([lm, q]) } catch { continue }
    let faces = (q.results ?? [])
    guard !faces.isEmpty else { continue }
    let sorted = faces.sorted { $0.boundingBox.height > $1.boundingBox.height }
    let main = sorted[0]
    let fh = main.boundingBox.height * H, fw = main.boundingBox.width * W
    if fh < 80 { continue }
    if sorted.count > 1 && sorted[1].boundingBox.height * H > fh * 0.45 { continue } // another prominent face
    if let roll = main.roll?.doubleValue, abs(roll) > 0.4 { continue }
    if let yaw = main.yaw?.doubleValue, abs(yaw) > 0.5 { continue }
    // face centre in top-left pixel coords
    let cx = (main.boundingBox.midX) * W
    let cy = (1 - main.boundingBox.midY) * H
    var side = max(fh, fw) * 2.1
    side = min(side, W, H)
    if side < max(fh, fw) * 1.5 { continue }
    var x = cx - side / 2, y = cy - side * 0.46
    x = min(max(0, x), W - side); y = min(max(0, y), H - side)
    guard let crop = img.cropping(to: CGRect(x: x, y: y, width: side, height: side).integral) else { continue }
    let ctx = CGContext(data: nil, width: outSize, height: outSize, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.interpolationQuality = .high
    ctx.draw(crop, in: CGRect(x: 0, y: 0, width: outSize, height: outSize))
    guard let out = ctx.makeImage() else { continue }
    let name = (f as NSString).deletingPathExtension + ".jpg"
    let dest = CGImageDestinationCreateWithURL(outDir.appendingPathComponent(name) as CFURL, UTType.jpeg.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, out, [kCGImageDestinationLossyCompressionQuality: 0.93] as CFDictionary)
    CGImageDestinationFinalize(dest)
    // dHash 9x8 on grayscale for near-duplicate detection
    let hctx = CGContext(data: nil, width: 9, height: 8, bitsPerComponent: 8, bytesPerRow: 9,
                         space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)!
    hctx.interpolationQuality = .medium
    hctx.draw(out, in: CGRect(x: 0, y: 0, width: 9, height: 8))
    let px = hctx.data!.bindMemory(to: UInt8.self, capacity: 72)
    var hash: UInt64 = 0
    for r in 0..<8 { for c in 0..<8 { hash <<= 1; if px[r*9+c] > px[r*9+c+1] { hash |= 1 } } }
    // 4x4 colour thumbnail for "same event" detection
    let cctx = CGContext(data: nil, width: 4, height: 4, bitsPerComponent: 8, bytesPerRow: 16,
                         space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    cctx.interpolationQuality = .medium
    cctx.draw(out, in: CGRect(x: 0, y: 0, width: 4, height: 4))
    let cp = cctx.data!.bindMemory(to: UInt8.self, capacity: 64)
    var col: [Int] = []
    for k in 0..<16 { col += [Int(cp[k*4]), Int(cp[k*4+1]), Int(cp[k*4+2])] }
    let quality = main.faceCaptureQuality ?? 0
    print("{\"src\":\"\(f)\",\"file\":\"\(name)\",\"quality\":\(quality),\"faceH\":\(Int(fh)),\"side\":\(Int(side)),\"hash\":\"\(String(hash, radix: 16))\",\"col\":\(col)}")
}
