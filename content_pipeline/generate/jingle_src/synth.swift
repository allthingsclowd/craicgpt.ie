// CraicGPT 80s-synth call-sign renderer (multitrack).
// Reads a JSON arrangement (bpm, tracks of GM-program notes + a drum track) and
// offline-renders it through Apple's built-in sampled GM synths — synth bass,
// synth brass, saw leads, polysynth, GM drum kit. Our composition, Apple's
// instruments, zero copyright. A shared plate reverb sits on the "wet" tracks
// (lead/pad) while bass + drums stay dry and punchy (that 80s separation).
//
// usage: synth <arrangement.json> <out.wav>
import AVFoundation
import Foundation

let a = CommandLine.arguments
guard a.count >= 3 else { FileHandle.standardError.write("usage: synth arr.json out.wav\n".data(using:.utf8)!); exit(2) }
let arrURL = URL(fileURLWithPath: a[1])
let outPath = a[2]

let data = try! Data(contentsOf: arrURL)
let json = try! JSONSerialization.jsonObject(with: data) as! [String: Any]
let bpm = (json["bpm"] as? Double) ?? 124.0
let reverbMix = Float((json["reverb"] as? Double) ?? 14.0)
let tracks = json["tracks"] as! [[String: Any]]
let spb = 60.0 / bpm   // seconds per beat

let dls = URL(fileURLWithPath: "/System/Library/Components/CoreAudio.component/Contents/Resources/gs_instruments.dls")
let sr = 44100.0
let fmt = AVAudioFormat(standardFormatWithSampleRate: sr, channels: 2)!

let engine = AVAudioEngine()
let reverb = AVAudioUnitReverb()
reverb.loadFactoryPreset(.plate)
reverb.wetDryMix = reverbMix
engine.attach(reverb)
engine.connect(reverb, to: engine.mainMixerNode, format: fmt)

struct Ev { let frame: Int; let on: Bool; let s: Int; let midi: UInt8; let vel: UInt8 }
var samplers: [AVAudioUnitSampler] = []
var events: [Ev] = []
var maxEnd = 0.0

for (i, t) in tracks.enumerated() {
    let s = AVAudioUnitSampler()
    engine.attach(s)
    let wet = (t["wet"] as? Bool) ?? false
    engine.connect(s, to: wet ? reverb : engine.mainMixerNode, format: fmt)
    let drum = (t["drum"] as? Bool) ?? false
    let program = UInt8((t["program"] as? Int) ?? 38)
    let bankMSB: UInt8 = drum ? 0x78 : 0x79
    try! s.loadSoundBankInstrument(at: dls, program: drum ? 0 : program, bankMSB: bankMSB, bankLSB: 0x00)
    if let g = t["gain"] as? Double {                 // linear gain -> dB
        s.overallGain = Float(max(-90.0, min(12.0, 20.0 * log10(max(0.0001, g)))))
    }
    samplers.append(s)
    let notes = t["notes"] as! [[Double]]             // [startBeat, durBeats, midi, vel]
    for n in notes {
        let startSec = n[0] * spb, durSec = max(0.04, n[1] * spb)
        let midi = UInt8(max(0, min(127, Int(n[2]))))
        let vel = UInt8(max(1, min(127, Int(n[3]))))
        events.append(Ev(frame: Int(startSec * sr), on: true,  s: i, midi: midi, vel: vel))
        events.append(Ev(frame: Int((startSec + durSec) * sr), on: false, s: i, midi: midi, vel: 0))
        maxEnd = max(maxEnd, startSec + durSec)
    }
}
events.sort { $0.frame < $1.frame }
let totalDur = maxEnd + 1.4   // synth release + reverb tail

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
var frame = 0, ei = 0
while frame < total {
    while ei < events.count && events[ei].frame <= frame {
        let e = events[ei]
        if e.on { samplers[e.s].startNote(e.midi, withVelocity: e.vel, onChannel: 0) }
        else    { samplers[e.s].stopNote(e.midi, onChannel: 0) }
        ei += 1
    }
    let nextEv = ei < events.count ? events[ei].frame : total
    let want = min(Int(maxFrames), max(1, nextEv - frame), total - frame)
    let status = try! engine.renderOffline(AVAudioFrameCount(want), to: buffer)
    if status == .success { try! outFile.write(from: buffer) }
    frame += want
}
FileHandle.standardError.write("rendered \(outPath) (\(String(format: "%.2f", totalDur))s)\n".data(using:.utf8)!)
