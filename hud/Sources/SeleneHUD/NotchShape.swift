import SwiftUI

public struct NotchShape: InsettableShape {
    public var topCornerRadius: CGFloat
    public var bottomCornerRadius: CGFloat
    public var insetAmount: CGFloat = 0

    public init(topCornerRadius: CGFloat = 6, bottomCornerRadius: CGFloat = 18, insetAmount: CGFloat = 0) {
        self.topCornerRadius = topCornerRadius
        self.bottomCornerRadius = bottomCornerRadius
        self.insetAmount = insetAmount
    }

    public func inset(by amount: CGFloat) -> NotchShape {
        var copy = self
        copy.insetAmount += amount
        return copy
    }

    public var animatableData: AnimatablePair<CGFloat, CGFloat> {
        get { .init(topCornerRadius, bottomCornerRadius) }
        set {
            topCornerRadius = newValue.first
            bottomCornerRadius = newValue.second
        }
    }

    public func path(in rect: CGRect) -> Path {
        let insetRect = rect.insetBy(dx: insetAmount, dy: insetAmount)
        var path = Path()
        path.move(to: CGPoint(x: insetRect.minX, y: insetRect.minY))

        // Left ear flare into top bezel (concave quad curve)
        path.addQuadCurve(
            to: CGPoint(x: insetRect.minX + topCornerRadius, y: insetRect.minY + topCornerRadius),
            control: CGPoint(x: insetRect.minX + topCornerRadius, y: insetRect.minY)
        )

        // Left vertical edge down to bottom curve
        path.addLine(to: CGPoint(x: insetRect.minX + topCornerRadius, y: insetRect.maxY - bottomCornerRadius))

        // Bottom-left rounded corner
        path.addQuadCurve(
            to: CGPoint(x: insetRect.minX + topCornerRadius + bottomCornerRadius, y: insetRect.maxY),
            control: CGPoint(x: insetRect.minX + topCornerRadius, y: insetRect.maxY)
        )

        // Bottom horizontal span
        path.addLine(to: CGPoint(x: insetRect.maxX - topCornerRadius - bottomCornerRadius, y: insetRect.maxY))

        // Bottom-right rounded corner
        path.addQuadCurve(
            to: CGPoint(x: insetRect.maxX - topCornerRadius, y: insetRect.maxY - bottomCornerRadius),
            control: CGPoint(x: insetRect.maxX - topCornerRadius, y: insetRect.maxY)
        )

        // Right vertical edge up to top curve
        path.addLine(to: CGPoint(x: insetRect.maxX - topCornerRadius, y: insetRect.minY + topCornerRadius))

        // Right ear flare into top bezel (concave quad curve)
        path.addQuadCurve(
            to: CGPoint(x: insetRect.maxX, y: insetRect.minY),
            control: CGPoint(x: insetRect.maxX - topCornerRadius, y: insetRect.minY)
        )

        path.addLine(to: CGPoint(x: insetRect.minX, y: insetRect.minY))
        return path
    }
}
