// CraicGPT call-sign renderer.
// Plays an ORIGINAL 5-note motif through Apple's built-in sampled GM instruments
// (the gs_instruments.dls bank that ships with macOS / drives GarageBand's GM),
// offline-rendered via AVAudioEngine with a touch of hall reverb for polish.
// Our notes, Apple's instruments — recognisable signature, zero copyright.
//
// usage: render <outPath.wav> <gmProgram 0-127> <transposeSemitones> <mode: call|resolve|drone>
import AVFoundation
import Foundation

let a = CommandLine.arguments
guard a.count >= 5 else { FileHandle.standardError.write("usage: render out prog transpose mode\n".data(using:.utf8)!); exit(2) }
let outPath = a[1]
let program = UInt8(a[2]) ?? 74
let transpose = Int(a[3]) ?? 0
let mode = a[4]

let dls = URL(fileURLWithPath: "/System/Library/Components/CoreAudio.component/Contents/Resources/gs_instruments.dls")
let sr = 44100.0
let fmt = AVAudioFormat(standardFormatWithSampleRate: sr, channels: 2)!

let engine = AVAudioEngine()
let sampler = AVAudioUnitSampler()
let reverb = AVAudioUnitReverb()
reverb.loadFactoryPreset(.mediumHall)
reverb.wetDryMix = 20            // subtle sheen, not a cathedral
engine.attach(sampler)
engine.attach(reverb)
engine.connect(sampler, to: reverb, format: fmt)
engine.connect(reverb, to: engine.mainMixerNode, format: fmt)

do {
    try sampler.loadSoundBankInstrument(at: dls, program: program, bankMSB: 0x79, bankLSB: 0x00)
} catch {
    FileHandle.standardError.write("load failed: \(error)\n".data(using:.utf8)!); exit(1)
}

// --- the motif --------------------------------------------------------------
// D major, do–mi–sol–la–sol : a bright, bugle-bright "good morning" call that
// rises and hangs on the 5th (an open question — perfect for a sign-on).
// 'resolve' swaps the last note home to do (a satisfied sign-off for the outro).
struct Note { let midi: Int; let start: Double; let dur: Double; let vel: UInt8 }
let doN = 74, mi = 78, sol = 81, la = 83   // D5 F#5 A5 B5
var motif: [Note]
switch mode {
case "drone":
    // a single held tonic (use under the band mix — e.g. bagpipe/fiddle drone)
    motif = [Note(midi: 50, start: 0.0, dur: 2.1, vel: 70)]   // D3
default:
    let lastNote = (mode == "resolve") ? doN : sol
    motif = [
        Note(midi: doN, start: 0.00, dur: 0.26, vel: 98),
        Note(midi: mi,  start: 0.24, dur: 0.26, vel: 96),
        Note(midi: sol, start: 0.48, dur: 0.44, vel: 112),
        Note(midi: la,  start: 0.90, dur: 0.26, vel: 100),
        Note(midi: lastNote, start: 1.14, dur: 0.80, vel: 110),
    ]
}
let tail = 1.0
let totalDur = (motif.map { $0.start + $0.dur }.max() ?? 2.0) + tail

// --- timed events (frame-accurate to the render block) ----------------------
struct Ev { let frame: Int; let on: Bool; let midi: UInt8; let vel: UInt8 }
var events: [Ev] = []
for n in motif {
    let m = UInt8(max(0, min(127, n.midi + (mode == "drone" ? 0 : transpose))))
    events.append(Ev(frame: Int(n.start * sr), on: true,  midi: m, vel: n.vel))
    events.append(Ev(frame: Int((n.start + n.dur) * sr), on: false, midi: m, vel: 0))
}
events.sort { $0.frame < $1.frame }

let maxFrames: AVAudioFrameCount = 4096
try! engine.enableManualRenderingMode(.offline, format: fmt, maximumFrameCount: maxFrames)
try! engine.start()

let settings: [String: Any] = [
    AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: sr, AVNumberOfChannelsKey: 2,
    AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false,
    AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false,
]
let outFile = try! AVAudioFile(forWriting: URL(fileURLWithPath: outPath), settings: settings,
                               commonFormat: .pcmFormatFloat32, interleaved: false)
let buffer = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: maxFrames)!

let total = Int(sr * totalDur)
var frame = 0
var ei = 0
while frame < total {
    while ei < events.count && events[ei].frame <= frame {
        let e = events[ei]
        if e.on { sampler.startNote(e.midi, withVelocity: e.vel, onChannel: 0) }
        else    { sampler.stopNote(e.midi, onChannel: 0) }
        ei += 1
    }
    let nextEv = ei < events.count ? events[ei].frame : total
    let want = min(Int(maxFrames), max(1, nextEv - frame), total - frame)
    let status = try! engine.renderOffline(AVAudioFrameCount(want), to: buffer)
    if status == .success { try! outFile.write(from: buffer) }
    frame += want
}
FileHandle.standardError.write("rendered \(outPath) (\(String(format: "%.2f", totalDur))s)\n".data(using:.utf8)!)
