// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "StackViewCore",
    platforms: [.macOS(.v13), .iOS(.v15)],
    products: [.library(name: "StackViewCore", targets: ["StackViewCore"])],
    targets: [
        .target(
            name: "StackViewCore",
            path: "stackviewtest",
            exclude: ["AppDelegate.swift", "ViewController.swift", "Info.plist", "Base.lproj", "Assets.xcassets", "en.lproj", "es.lproj", "PrivacyInfo.xcprivacy"],
            sources: ["StackItem.swift", "ItemRepository.swift", "JourneyStore.swift"]
        ),
        .testTarget(name: "StackViewCoreTests", dependencies: ["StackViewCore"], path: "Tests/StackViewCoreTests")
    ]
)
