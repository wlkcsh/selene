// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "SeleneHUD",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "SeleneHUD",
            targets: ["SeleneHUD"]
        )
    ],
    targets: [
        .executableTarget(
            name: "SeleneHUD",
            path: "Sources/SeleneHUD"
        )
    ]
)
