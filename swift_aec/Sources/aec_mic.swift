// aec_mic — captures the system microphone with Apple AUVoiceProcessingIO
// (the AEC engine FaceTime / iMessage / Continuity Camera ship), resamples
// to mono PCM16 @ 16 kHz, and writes the raw bytes to stdout in real time.
//
// Python side (voice-realtime --aec-backend swift) spawns this binary, reads
// stdin-of-subprocess as a never-ending PCM16 stream, and feeds it to the
// realtime provider — replacing the sounddevice MicrophoneStream while the
// session is active. The voiceProcessing flag tells CoreAudio to run its
// own echo cancellation + noise suppression in the audio driver, using the
// system speaker output as the reference signal automatically.
//
// stderr is for log lines ("ready", "starting", error messages). Python
// surfaces those in its own log file.
//
// Build:
//   swiftc -O -o build/aec_mic Sources/aec_mic.swift
//
// Run (manual smoke test, writes PCM16 to /tmp/aec_mic.raw for 5s):
//   ./build/aec_mic > /tmp/aec_mic.raw &
//   sleep 5; kill %1
//   ffplay -f s16le -ar 16000 -ac 1 /tmp/aec_mic.raw

import AVFoundation
import Foundation

let kTargetSampleRate: Double = 16_000
let kTargetChannels: AVAudioChannelCount = 1

func logErr(_ s: String) {
    FileHandle.standardError.write(Data((s + "\n").utf8))
}

// Explicit TCC microphone permission request. Without an associated app
// bundle + NSMicrophoneUsageDescription, this returns .denied silently and
// the input node will emit silence. Use requestAccess so the OS at least
// surfaces the actual status before the engine starts.
let semaphore = DispatchSemaphore(value: 0)
var permissionStatus: AVAuthorizationStatus = .notDetermined
let initialStatus = AVCaptureDevice.authorizationStatus(for: .audio)
logErr("mic permission status (initial): \(initialStatus.rawValue) \(initialStatus)")
if initialStatus == .notDetermined {
    AVCaptureDevice.requestAccess(for: .audio) { granted in
        permissionStatus = granted ? .authorized : .denied
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 5.0)
    logErr("mic permission status (after request): \(permissionStatus.rawValue) \(permissionStatus)")
} else {
    permissionStatus = initialStatus
}
if permissionStatus != .authorized {
    logErr("mic permission NOT granted — engine will emit silence. Approve in System Settings → Privacy → Microphone for the parent process or sign this binary with NSMicrophoneUsageDescription.")
}

let engine = AVAudioEngine()
let input = engine.inputNode

// Enable Apple's AUVoiceProcessingIO. This must be set BEFORE the engine
// starts and BEFORE any tap is installed. Fails on devices without the AU
// (very rare on macOS) — caller falls back to pyaec or sounddevice.
do {
    try input.setVoiceProcessingEnabled(true)
} catch {
    logErr("setVoiceProcessingEnabled failed: \(error.localizedDescription)")
    exit(2)
}

let inputFormat = input.outputFormat(forBus: 0)
logErr("input bus format: rate=\(inputFormat.sampleRate) ch=\(inputFormat.channelCount) interleaved=\(inputFormat.isInterleaved)")

guard let outFormat = AVAudioFormat(
    commonFormat: .pcmFormatInt16,
    sampleRate: kTargetSampleRate,
    channels: kTargetChannels,
    interleaved: true
) else {
    logErr("could not build output format")
    exit(3)
}

// Intermediate mono float32 buffer @ the device's native rate. The input bus
// exposes the MBP mic array as 7-channel non-interleaved float32 — feeding
// that straight into AVAudioConverter for downmix + resample produces all
// zeros (the converter silently doesn't know how to fold 7 raw channels).
// Downmixing to channel 0 ourselves then converting mono → mono works.
guard let monoFormat = AVAudioFormat(
    commonFormat: .pcmFormatFloat32,
    sampleRate: inputFormat.sampleRate,
    channels: 1,
    interleaved: false
) else {
    logErr("could not build mono intermediate format")
    exit(3)
}

guard let converter = AVAudioConverter(from: monoFormat, to: outFormat) else {
    logErr("AVAudioConverter init failed")
    exit(4)
}

let stdout = FileHandle.standardOutput

// AVAudioConverter needs a sized output buffer per pull. Size it to roughly
// 100 ms of target audio so we don't allocate every callback — way more than
// the 10 ms input buffer will ever need.
let outCapacity = AVAudioFrameCount(kTargetSampleRate / 10)

input.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { (buffer: AVAudioPCMBuffer, _: AVAudioTime) in
    // Downmix to a mono float32 buffer at the device rate before letting the
    // AVAudioConverter resample to 16 kHz int16. The MBP Air mic array
    // exposes 7 non-interleaved channels and AVAudioConverter silently
    // produces zeros if asked to fold all of them itself — copying channel
    // 0 first (the canonical post-voiceProcessing feed) sidesteps this.
    guard let monoBuffer = AVAudioPCMBuffer(pcmFormat: monoFormat, frameCapacity: buffer.frameLength),
          let src = buffer.floatChannelData,
          let dst = monoBuffer.floatChannelData else {
        return
    }
    monoBuffer.frameLength = buffer.frameLength
    memcpy(dst[0], src[0], Int(buffer.frameLength) * MemoryLayout<Float>.size)

    guard let outBuffer = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: outCapacity) else { return }
    var error: NSError?
    var supplied = false
    let status = converter.convert(to: outBuffer, error: &error) { _, inputStatusPointer in
        if supplied {
            inputStatusPointer.pointee = .noDataNow
            return nil
        }
        supplied = true
        inputStatusPointer.pointee = .haveData
        return monoBuffer
    }
    if status == .error || error != nil {
        logErr("convert error: \(error?.localizedDescription ?? "unknown")")
        return
    }
    guard let chan = outBuffer.int16ChannelData?[0], outBuffer.frameLength > 0 else { return }
    let frames = Int(outBuffer.frameLength)
    let byteCount = frames * MemoryLayout<Int16>.size
    chan.withMemoryRebound(to: UInt8.self, capacity: byteCount) { ptr in
        stdout.write(Data(bytes: ptr, count: byteCount))
    }
}

do {
    try engine.start()
} catch {
    logErr("engine.start failed: \(error.localizedDescription)")
    exit(5)
}

logErr("aec_mic ready — streaming PCM16 mono @ \(Int(kTargetSampleRate)) Hz to stdout")

// Clean shutdown on SIGTERM/SIGINT so the parent (Python) can stop us.
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

RunLoop.main.run()
