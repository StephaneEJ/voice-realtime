// ─────────────────────────────────────────────────────────────────────────
// Tokens.swift — voice-realtime macOS design tokens
// Port of design/midfi.css (mid-fidelity visual system, warm dark).
//
// DRAFT: text-only port written before Session 0 SwiftUI scaffold exists.
// Will move to `ui-macos/Sources/VoiceRTApp/Resources/Tokens.swift` during
// Session 0. No Xcode project yet → not compiled yet → review-only.
//
// All public surface is `enum Mf` namespaces — no class/struct holding state.
// Use as `Mf.Color.bg`, `Mf.Typo.title`, `Mf.Space.s8`, etc.
// ─────────────────────────────────────────────────────────────────────────

import SwiftUI

public enum Mf {

    // ─── Colors ────────────────────────────────────────────────────────────
    // All hex literals correspond 1:1 to midfi.css `--mf-*` custom properties.

    public enum Color {
        // Surfaces (warm dark)
        public static let bg      = SwiftUI.Color(hex: 0x14161B)
        public static let panel   = SwiftUI.Color(hex: 0x1A1D23)
        public static let panel2  = SwiftUI.Color(hex: 0x20242C)
        public static let panel3  = SwiftUI.Color(hex: 0x262B34)

        // Borders / strokes — white at low alpha layered over surfaces
        public static let border  = SwiftUI.Color.white.opacity(0.06)
        public static let border2 = SwiftUI.Color.white.opacity(0.10)
        public static let stroke  = SwiftUI.Color.white.opacity(0.14)

        // Foreground (text)
        public static let fg   = SwiftUI.Color(hex: 0xECEDEF)  // primary text
        public static let fg2  = SwiftUI.Color(hex: 0xC4C7CD)  // secondary text
        public static let dim  = SwiftUI.Color(hex: 0x8D929C)  // muted / captions
        public static let mute = SwiftUI.Color(hex: 0x5C6068)  // placeholders, very dim

        // Accent (primary CTA, live indicators, links)
        public static let acc     = SwiftUI.Color(hex: 0x4FC3F7)
        public static let acc2    = SwiftUI.Color(hex: 0x29B3F3)  // hover/strong
        public static let accSoft = SwiftUI.Color(red: 79/255,  green: 195/255, blue: 247/255, opacity: 0.14)
        public static let accGlow = SwiftUI.Color(red: 79/255,  green: 195/255, blue: 247/255, opacity: 0.35)

        // Status
        public static let warn       = SwiftUI.Color(hex: 0xFFB74D)
        public static let warnSoft   = SwiftUI.Color(red: 255/255, green: 183/255, blue: 77/255,  opacity: 0.14)
        public static let danger     = SwiftUI.Color(hex: 0xFF7676)
        public static let dangerSoft = SwiftUI.Color(red: 255/255, green: 118/255, blue: 118/255, opacity: 0.14)
        public static let ok         = SwiftUI.Color(hex: 0x80E27E)
        public static let okSoft     = SwiftUI.Color(red: 128/255, green: 226/255, blue: 126/255, opacity: 0.14)

        // Per-persona accent tints (avatars, chips). String keys must match
        // persona slugs in `_System/voice-personas/<slug>.md`.
        public static let personaTints: [String: SwiftUI.Color] = [
            "aria": SwiftUI.Color(hex: 0xFF8A7A),
            "koda": SwiftUI.Color(hex: 0x4FC3F7),
            "mira": SwiftUI.Color(hex: 0xC084FC),
            "noor": SwiftUI.Color(hex: 0x5EEAD4),
            "zen":  SwiftUI.Color(hex: 0xA3E635),
            "fox":  SwiftUI.Color(hex: 0xFFB74D),
        ]

        /// Returns the persona's accent tint, falling back to `acc` if unknown.
        public static func personaTint(_ slug: String) -> SwiftUI.Color {
            personaTints[slug.lowercased()] ?? acc
        }
    }

    // ─── Typography ────────────────────────────────────────────────────────
    // SF Pro Display for headers, SF Pro Text for body, JetBrains Mono for metrics.
    // On macOS, `.system` resolves to SF Pro automatically. JetBrains Mono is
    // bundled in `Resources/Fonts/` (see Session 0 scaffold checklist).

    public enum Typo {
        public static let display = Font.system(size: 22, weight: .semibold).leading(.tight)
        public static let title   = Font.system(size: 16, weight: .semibold)
        public static let subtitle = Font.system(size: 13, weight: .medium)
        public static let body    = Font.system(size: 13, weight: .regular)
        public static let label   = Font.system(size: 11, weight: .medium)  // ALL CAPS in views
        public static let cap     = Font.system(size: 11, weight: .regular)
        public static let mono    = Font.custom("JetBrains Mono", size: 11, relativeTo: .caption)
        public static let mono12  = Font.custom("JetBrains Mono", size: 12, relativeTo: .caption)

        /// Tracking values (letter-spacing in CSS px → SwiftUI .tracking in points).
        public enum Tracking {
            public static let displayTight: CGFloat = -0.4   // -0.018em @ 22px
            public static let titleTight:   CGFloat = -0.16  // -0.01em  @ 16px
            public static let bodyTight:    CGFloat = -0.07  // -0.005em @ 13px
            public static let labelWide:    CGFloat = 0.22   // 0.02em   @ 11px (ALL CAPS)
        }
    }

    // ─── Spacing scale ─────────────────────────────────────────────────────
    // Inferred from midfi.css gap/padding usage. Scale snaps to 2px steps.
    // Use the named tokens to keep all spacing consistent across views.

    public enum Space {
        public static let s2:  CGFloat = 2
        public static let s4:  CGFloat = 4
        public static let s6:  CGFloat = 6
        public static let s8:  CGFloat = 8     // default row gap
        public static let s10: CGFloat = 10
        public static let s12: CGFloat = 12    // popover padding
        public static let s14: CGFloat = 14
        public static let s16: CGFloat = 16
        public static let s20: CGFloat = 20
        public static let s24: CGFloat = 24
        public static let s32: CGFloat = 32
    }

    // ─── Radii ─────────────────────────────────────────────────────────────

    public enum Radius {
        public static let chip:    CGFloat = 6   // .mf-chip
        public static let control: CGFloat = 8   // .mf-switcher, segmented
        public static let card:    CGFloat = 12  // .mf default
        public static let popover: CGFloat = 14  // .mf.popover
        public static let pill:    CGFloat = .infinity  // capsule
    }

    // ─── Avatar sizes ──────────────────────────────────────────────────────
    // sm/md/lg/xl/xxl mirror `.mf-av.<size>` in midfi.css.

    public enum AvatarSize {
        public static let sm:  CGFloat = 22
        public static let md:  CGFloat = 32
        public static let lg:  CGFloat = 48
        public static let xl:  CGFloat = 80
        public static let xxl: CGFloat = 112   // overlay sidebar
    }

    // ─── Motion ────────────────────────────────────────────────────────────
    // Durations match midfi.css transition values. Use Animation.easeInOut(...)
    // unless a specific curve is documented in design/midfi-anim.jsx.

    public enum Motion {
        public static let fast: Double      = 0.08   // press feedback
        public static let standard: Double  = 0.12   // hover, color swaps
        public static let smooth: Double    = 0.16   // toggle/slider thumb
        public static let pulseSlow: Double = 1.6    // avatar live ring
        public static let blink: Double     = 1.4    // live dot chip

        /// Default easing for hover/state transitions.
        public static let standardAnim = Animation.easeInOut(duration: standard)
        public static let smoothAnim   = Animation.easeInOut(duration: smooth)
        public static let pulseAnim    = Animation.easeOut(duration: pulseSlow).repeatForever(autoreverses: false)
    }

    // ─── Layout constants ──────────────────────────────────────────────────
    // Frame sizes from design/midfi-main.jsx + midfi-settings.jsx.

    public enum Layout {
        public static let popoverWidth:    CGFloat = 400
        public static let popoverHeight:   CGFloat = 600
        public static let settingsWidth:   CGFloat = 500
        public static let settingsHeight:  CGFloat = 700
        public static let personaEditorW:  CGFloat = 520
        public static let overlayRatio:    CGFloat = 0.30   // 30% screen width
        public static let headerHeight:    CGFloat = 38
    }
}

// ─── SwiftUI.Color hex extension ───────────────────────────────────────────
// Convenience initializer matching the CSS literal style used in midfi.css.

public extension SwiftUI.Color {
    /// Initializes a Color from a 0xRRGGBB integer literal. Alpha defaults to 1.
    init(hex: UInt32, opacity: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8)  & 0xFF) / 255.0
        let b = Double( hex        & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: opacity)
    }
}
