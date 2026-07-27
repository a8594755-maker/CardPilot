import AVFoundation

// MARK: - Sound Effect Manager

@Observable
final class SoundManager {
    static let shared = SoundManager()

    var isMuted = false
    private var players: [String: AVAudioPlayer] = [:]

    private init() {}

    func play(_ sound: Sound) {
        guard !isMuted else { return }

        if let player = players[sound.rawValue] {
            player.currentTime = 0
            player.play()
            return
        }

        guard let url = Bundle.main.url(forResource: sound.rawValue, withExtension: "mp3") else {
            return
        }

        do {
            let player = try AVAudioPlayer(contentsOf: url)
            player.prepareToPlay()
            player.play()
            players[sound.rawValue] = player
        } catch {
            print("[Sound] Failed to play \(sound.rawValue): \(error)")
        }
    }

    enum Sound: String {
        case deal
        case check
        case chipBet = "chip_bet"
        case chipWin = "chip_win"
        case fold
        case allIn = "all_in"
        case timer
        case notification
    }
}
