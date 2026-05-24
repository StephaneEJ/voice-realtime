// ─────────────────────────────────────────────────────────────────────────
// Models.swift — voice-realtime macOS data models
// DRAFT: text-only port. Will move to `ui-macos/Sources/VoiceRTApp/Models/`
// (one file per type) during Session 0 scaffold.
//
// These types are CONTRACTS shared by all parallel sessions (A-G). Once
// merged, changing any field requires coordination — treat as frozen.
//
// Wire format mirrors the WS schema in voice_realtime/control_server.py.
// Decoder strategy: JSONDecoder with .convertFromSnakeCase NOT used, because
// the backend already emits camelCase (sessionId, personaId, etc.).
// ─────────────────────────────────────────────────────────────────────────

import Foundation

// ─── Persona ───────────────────────────────────────────────────────────────
// Echoes the `personas.list` WS event payload + local edit fields.

public struct Persona: Identifiable, Hashable, Codable {
    public let id: String          // slug, primary key
    public var name: String
    public var description: String
    public var voice: String?
    public var model: String?
    public var provider: Provider?   // gemini | openai | nil (= use default)
    public var vad: VADPreset?
    public var avatar: String?       // vault path or asset name
    public var hasObsidianFilter: Bool

    public enum Provider: String, Codable, CaseIterable {
        case gemini
        case openai
    }

    public enum VADPreset: String, Codable, CaseIterable {
        case reactive
        case balanced
        case patient
        case veryPatient = "very-patient"
    }
}

// ─── Session state machine ────────────────────────────────────────────────
// State enum drives top-level UI routing (welcome vs active vs error).
// Transitions are documented in design/README.md state diagram.

public enum SessionState: Equatable {
    case idle
    case connecting
    case live
    case muted
    case stopping
    case reconnecting(attempt: Int)
    case error(code: String, message: String)
}

// ─── Metrics ──────────────────────────────────────────────────────────────
// Live numbers shown in the active session strip + overlay sidebar.
// Updated reactively from `cost.tick` + `ttfa` / `ttfi` WS events.

public struct SessionMetrics: Equatable {
    public var durationSeconds: Double = 0
    public var costUsd: Double = 0
    public var ttfaMs: Double? = nil     // time-to-first-audio
    public var ttfiMs: Double? = nil     // time-to-first-interrupt
    public var tokensIn: Int = 0         // future — not yet emitted
    public var tokensOut: Int = 0        // future — not yet emitted

    /// Formats duration as "mm:ss". Caps at 99:59 to keep the strip width stable.
    public var durationLabel: String {
        let total = min(Int(durationSeconds), 99 * 60 + 59)
        return String(format: "%02d:%02d", total / 60, total % 60)
    }

    /// Formats cost as "$0.42" with 2-decimal precision.
    public var costLabel: String {
        String(format: "$%.2f", costUsd)
    }
}

// ─── Transcript ───────────────────────────────────────────────────────────

public struct TranscriptTurn: Identifiable, Equatable {
    public let id = UUID()
    public let role: Role
    public var text: String
    public var partial: Bool
    public let createdAt: Date

    public enum Role: String, Codable {
        case user
        case model
    }
}

// ─── VU levels ────────────────────────────────────────────────────────────
// Rolling buffer of the last 32 RMS values per side. Drives the radial
// spectrum animation in ActiveSession view.

public struct VULevels: Equatable {
    public static let bufferSize = 32
    public private(set) var user: [Float] = Array(repeating: 0, count: bufferSize)
    public private(set) var model: [Float] = Array(repeating: 0, count: bufferSize)

    public mutating func pushUser(_ rms: Float) {
        user.removeFirst()
        user.append(min(1.0, max(0.0, rms)))
    }

    public mutating func pushModel(_ rms: Float) {
        model.removeFirst()
        model.append(min(1.0, max(0.0, rms)))
    }
}

// ─── Budget / settings persisted to disk ──────────────────────────────────

public struct AppSettings: Codable, Equatable {
    public var defaultModel: String = "gemini-2.5-flash-native-audio-latest"
    public var budgetCapUsd: Double = 22.0
    public var alertAt80Percent: Bool = true
    public var activePersonaId: String = "jarvis"
}

// ─── WS error envelope ────────────────────────────────────────────────────
// Matches `{"ev": "error", "code": ..., "msg": ...}` from control_server.py.

public struct WSError: Codable, Equatable {
    public let code: String
    public let message: String

    public enum CodingKeys: String, CodingKey {
        case code
        case message = "msg"
    }
}
