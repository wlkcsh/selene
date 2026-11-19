import AppKit
import CoreGraphics

func renderIcon(size: Int) -> NSImage {
    let s = CGFloat(size)
    let img = NSImage(size: NSSize(width: s, height: s))
    img.lockFocus()

    guard let ctx = NSGraphicsContext.current?.cgContext else {
        img.unlockFocus()
        return img
    }

    // 1. Draw rounded squircle background
    let rect = CGRect(x: s * 0.05, y: s * 0.05, width: s * 0.90, height: s * 0.90)
    let cornerRadius = s * 0.22
    let path = CGPath(roundedRect: rect, cornerWidth: cornerRadius, cornerHeight: cornerRadius, transform: nil)

    ctx.saveGState()
    ctx.addPath(path)
    ctx.clip()

    // Cosmic background gradient
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let bgColors = [
        NSColor(red: 0.12, green: 0.06, blue: 0.24, alpha: 1.0).cgColor,
        NSColor(red: 0.05, green: 0.02, blue: 0.12, alpha: 1.0).cgColor
    ] as CFArray
    if let bgGradient = CGGradient(colorsSpace: colorSpace, colors: bgColors, locations: [0.0, 1.0]) {
        ctx.drawLinearGradient(bgGradient, start: CGPoint(x: 0, y: s), end: CGPoint(x: s, y: 0), options: [])
    }
    ctx.restoreGState()

    // Subtle border
    ctx.saveGState()
    ctx.addPath(path)
    ctx.setStrokeColor(NSColor(red: 0.8, green: 0.5, blue: 1.0, alpha: 0.35).cgColor)
    ctx.setLineWidth(max(1.0, s * 0.015))
    ctx.strokePath()
    ctx.restoreGState()

    // 2. Draw glowing crescent moon ("Selene")
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -s * 0.02), blur: s * 0.08, color: NSColor(red: 0.85, green: 0.45, blue: 1.0, alpha: 0.6).cgColor)

    let moonPath = CGMutablePath()
    let center = CGPoint(x: s * 0.52, y: s * 0.50)
    let outerRadius = s * 0.26
    let innerRadius = s * 0.22

    moonPath.addArc(center: center, radius: outerRadius, startAngle: -0.8, endAngle: 2.2, clockwise: false)
    let innerCenter = CGPoint(x: s * 0.59, y: s * 0.53)
    moonPath.addArc(center: innerCenter, radius: innerRadius, startAngle: 2.0, endAngle: -0.6, clockwise: true)
    moonPath.closeSubpath()

    ctx.addPath(moonPath)
    ctx.clip()

    let moonColors = [
        NSColor(red: 1.00, green: 0.72, blue: 0.95, alpha: 1.0).cgColor,
        NSColor(red: 0.75, green: 0.45, blue: 1.00, alpha: 1.0).cgColor
    ] as CFArray
    if let moonGradient = CGGradient(colorsSpace: colorSpace, colors: moonColors, locations: [0.0, 1.0]) {
        ctx.drawLinearGradient(moonGradient, start: CGPoint(x: s * 0.3, y: s * 0.8), end: CGPoint(x: s * 0.7, y: s * 0.2), options: [])
    }
    ctx.restoreGState()

    // 3. Draw Sparkles
    func drawSparkle(center: CGPoint, radius: CGFloat) {
        ctx.saveGState()
        ctx.setShadow(offset: .zero, blur: radius * 1.5, color: NSColor(red: 1.0, green: 0.8, blue: 1.0, alpha: 0.8).cgColor)
        ctx.setFillColor(NSColor.white.cgColor)

        let star = CGMutablePath()
        star.move(to: CGPoint(x: center.x, y: center.y - radius))
        star.addQuadCurve(to: CGPoint(x: center.x + radius, y: center.y), control: center)
        star.addQuadCurve(to: CGPoint(x: center.x, y: center.y + radius), control: center)
        star.addQuadCurve(to: CGPoint(x: center.x - radius, y: center.y), control: center)
        star.addQuadCurve(to: CGPoint(x: center.x, y: center.y - radius), control: center)
        star.closeSubpath()

        ctx.addPath(star)
        ctx.fillPath()
        ctx.restoreGState()
    }

    drawSparkle(center: CGPoint(x: s * 0.35, y: s * 0.65), radius: s * 0.065)
    drawSparkle(center: CGPoint(x: s * 0.70, y: s * 0.35), radius: s * 0.045)
    drawSparkle(center: CGPoint(x: s * 0.65, y: s * 0.72), radius: s * 0.035)

    img.unlockFocus()
    return img
}

let fm = FileManager.default
let iconsetDir = URL(fileURLWithPath: "Selene.iconset")
try? fm.removeItem(at: iconsetDir)
try fm.createDirectory(at: iconsetDir, withIntermediateDirectories: true)

let sizes: [(String, Int)] = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

for (name, px) in sizes {
    let img = renderIcon(size: px)
    if let tiff = img.tiffRepresentation,
       let rep = NSBitmapImageRep(data: tiff),
       let png = rep.representation(using: .png, properties: [:]) {
        let dest = iconsetDir.appendingPathComponent(name)
        try png.write(to: dest)
    }
}
print("✨ Iconset generated successfully at \(iconsetDir.path)")
