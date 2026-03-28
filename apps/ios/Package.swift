// swift-tools-version: 5.9
// CardPilot iOS — SPM Dependencies
// Use this file to resolve dependencies, then add them to the Xcode project.

import PackageDescription

let package = Package(
    name: "CardPilotDeps",
    platforms: [.iOS(.v17)],
    dependencies: [
        .package(url: "https://github.com/socketio/socket.io-client-swift", from: "16.1.1"),
        .package(url: "https://github.com/supabase/supabase-swift", from: "2.0.0"),
    ],
    targets: [
        .target(
            name: "CardPilotDeps",
            dependencies: [
                .product(name: "SocketIO", package: "socket.io-client-swift"),
                .product(name: "Supabase", package: "supabase-swift"),
            ]
        ),
    ]
)
